import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role, notify
from apps.core.permissions import role_permission
from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store, stores_in_county

from . import inventory
from .commerce import ShopBundle, ShopBundleItem
from .models import ShopCategory, ShopProduct

# کارشناسانی که نرخ سایر کالاها (کالاهای غیراساسی) را تایید می‌کنند
SHOP_REVIEWER_ROLES = (Role.SAMT, Role.ADMIN)

# تغییر هر یک از این فیلدها محصول را دوباره به صف تایید می‌برد
REVIEWABLE_FIELDS = ("name", "price", "old_price", "unit", "brand", "description")


class ShopCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopCategory
        fields = ["id", "name", "icon", "order"]


class ShopProductSerializer(serializers.ModelSerializer):
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    store_name = serializers.CharField(source="store.name", read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    union_name = serializers.CharField(source="store.union.name", read_only=True, default="")
    sold_out = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShopProduct
        fields = [
            "id", "store", "store_name", "union_name", "category", "category_name", "name", "description", "image",
            "price", "old_price", "discount_percent", "unit", "unit_display", "brand",
            "is_available", "is_active", "order", "created_at",
            "status", "status_display", "reviewed_at", "review_note", "is_special",
            "stock", "per_user_limit", "sold_out", "sku", "min_stock", "shelf", "cost_price",
        ]
        # قیمت تمام‌شده فقط از فاکتور خرید به‌روز می‌شود
        read_only_fields = ["store", "status", "reviewed_at", "review_note", "cost_price"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # موجودی دقیق انبار فقط برای صاحب فروشگاه و مسئولان است؛ مشتری فقط «ناموجود» را می‌بیند
        user = getattr(self.context.get("request"), "user", None)
        # (مسئولان سطح‌های بالاتر فقط مشخصات عمومی و وضعیت تایید را می‌بینند، نه موجودی و قیمت تمام‌شده)
        staff = bool(user and user.is_authenticated and (user.role == Role.ADMIN or instance.store.owner_id == user.pk))
        if not staff:
            for k in ("stock", "cost_price", "min_stock", "shelf"):
                data.pop(k, None)
        return data

    def validate_price(self, v):
        if v < 1000:
            raise serializers.ValidationError("قیمت باید دست‌کم ۱٬۰۰۰ ریال (۱۰۰ تومان) باشد.")
        return v

    def validate_per_user_limit(self, v):
        if v is not None and v < 1:
            raise serializers.ValidationError("سقف خرید باید دست‌کم ۱ باشد (یا خالی بگذارید).")
        return v

    def validate(self, attrs):
        special = attrs.get("is_special", getattr(self.instance, "is_special", False))
        if special:
            price = attrs.get("price", getattr(self.instance, "price", None))
            old = attrs.get("old_price", getattr(self.instance, "old_price", None))
            if not old or not price or old <= price:
                raise serializers.ValidationError(
                    {"old_price": "برای تخفیف ویژه، قیمت اصلی باید از قیمت با تخفیف بیشتر باشد."})
        return attrs


class ShopCategoryViewSet(viewsets.ModelViewSet):
    queryset = ShopCategory.objects.all()
    serializer_class = ShopCategorySerializer
    pagination_class = None

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [role_permission("admin")()]


class MyShopProductViewSet(ScopedModelViewSet):
    """مدیریت محصولات فروشگاه اینترنتی توسط خود فروشگاه (و نظارت سطوح بالاتر)."""

    queryset = ShopProduct.objects.select_related("store", "category")
    serializer_class = ShopProductSerializer
    read_roles = ("governorate", "samt", "chamber", "union", "store")
    write_roles = ("store",)
    filterset_fields = ["category", "is_active", "is_available", "store", "is_special"]
    search_fields = ["name", "brand", "description"]

    def _my_store(self) -> Store:
        store = self.request.user.stores.first()
        if not store:
            raise ValidationError({"detail": "ابتدا فروشگاه خود را ثبت کنید."})
        if store.status != Store.Status.ACTIVE:
            raise ValidationError({"detail": "فروشگاه شما هنوز فعال نشده است."})
        return store

    def perform_create(self, serializer):
        store = self._my_store()
        # فروشگاه ویژه بدون تایید صمت عرضه می‌کند
        status = ShopProduct.Status.APPROVED if store.is_featured else ShopProduct.Status.PENDING
        # در فروشگاه ویژه موجودی اولیه به‌صورت «موجودی اولیه» در دفتر انبار ثبت می‌شود
        opening = serializer.validated_data.pop("stock", None) if store.is_featured else None
        product = self._save_in_scope(serializer, store=store, status=status)
        if opening:
            inventory.record(product.pk, opening, inventory.Kind.OPENING, note="موجودی اولیه", by=self.request.user)
            product.refresh_from_db()
        if not store.is_featured:
            self._notify_reviewers(product, "محصول جدید در انتظار تایید")

    def perform_update(self, serializer):
        serializer.validated_data.pop("store", None)
        # ویرایش نام یا قیمت، محصول را دوباره به صف تایید کارشناس صمت می‌برد
        instance = serializer.instance
        changed = any(
            f in serializer.validated_data and serializer.validated_data[f] != getattr(instance, f)
            for f in REVIEWABLE_FIELDS
        )
        reviewed = changed and not instance.store.is_featured
        new_stock = None
        if instance.store.is_featured and "stock" in serializer.validated_data:
            # تغییر موجودی در فروشگاه ویژه فقط از طریق دفتر انبار (تعدیل) انجام می‌شود
            wanted = serializer.validated_data.pop("stock")
            if wanted is not None and wanted != instance.stock:
                new_stock = wanted
        extra = {"status": ShopProduct.Status.PENDING, "reviewed_at": None, "review_note": ""} if reviewed else {}
        product = self._save_in_scope(serializer, **extra)
        if new_stock is not None:
            kind = inventory.Kind.OPENING if instance.stock is None else inventory.Kind.ADJUST
            inventory.adjust(product, set_to=new_stock, kind=kind, note="ویرایش موجودی از فرم کالا", by=self.request.user)
            product.refresh_from_db()
        if reviewed:
            self._notify_reviewers(product, "تغییر قیمت/مشخصات محصول در انتظار تایید")

    def _notify_reviewers(self, product: ShopProduct, title: str) -> None:
        from apps.accounts.models import User

        union = product.store.union or product.store.covered_unions.first()
        if not union:
            return
        province = union.chamber.county.province_id
        reviewers = User.objects.filter(role=Role.SAMT, province_id=province)
        notify(reviewers, title,
               f"«{product.name}» از فروشگاه {product.store.name} — {product.price:,} ریال",
               "/panel/other-prices")


@api_view(["GET"])
@permission_classes([AllowAny])
def public_shop(request, pk):
    """ویترین فروشگاه اینترنتی یک فروشگاه برای نمایش عمومی."""
    from .order_services import expire_unpaid_orders

    store = get_object_or_404(Store, pk=pk, status=Store.Status.ACTIVE)
    if store.is_featured:
        expire_unpaid_orders(store, limit=50)       # موجودی نگه‌داشته‌شده‌ی سفارش‌های رهاشده آزاد شود
    qs = store.shop_products.filter(
        is_active=True, status=ShopProduct.Status.APPROVED
    ).select_related("category", "store__union")
    if (category := request.query_params.get("category", "")).isdigit():
        qs = qs.filter(category_id=int(category))
    if q := request.query_params.get("q"):
        qs = qs.filter(name__icontains=q[:80])
    return Response(ShopProductSerializer(qs[:300], many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_shop_products(request):
    """جستجوی محصولات فروشگاهی در میان همه فروشگاه‌های فعال (ویترین سراسری)."""
    from apps.core.pagination import Pagination

    qs = ShopProduct.objects.filter(
        is_active=True, is_available=True, status=ShopProduct.Status.APPROVED,
        store__status=Store.Status.ACTIVE,
    ).select_related("store__union", "category")
    if (county := request.query_params.get("county", "")).isdigit():
        qs = stores_in_county(qs, int(county), prefix="store__")
    if (category := request.query_params.get("category", "")).isdigit():
        qs = qs.filter(category_id=int(category))
    if q := request.query_params.get("q"):
        qs = qs.filter(name__icontains=q[:80])
    ordering = {"price": "price", "-price": "-price", "recent": "-created_at"}.get(
        request.query_params.get("ordering"), "-created_at"
    )
    paginator = Pagination()
    page = paginator.paginate_queryset(qs.order_by(ordering), request)
    return paginator.get_paginated_response(ShopProductSerializer(page, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_shop_summary(request):
    """خلاصه وضعیت فروشگاه اینترنتی برای داشبورد فروشگاه."""
    store = request.user.stores.first()
    if not store:
        return Response({"total": 0, "available": 0, "hidden": 0})
    qs = store.shop_products.all()
    return Response({
        "total": qs.count(),
        "available": qs.filter(is_active=True, is_available=True,
                               status=ShopProduct.Status.APPROVED).count(),
        "hidden": qs.filter(is_active=False).count(),
        "pending": qs.filter(status=ShopProduct.Status.PENDING).count(),
        "rejected": qs.filter(status=ShopProduct.Status.REJECTED).count(),
    })


class ShopPriceReviewViewSet(ScopedModelViewSet):
    """کارتابل «نرخ سایر کالاها» — بررسی و تایید قیمت کالاهای غیراساسی توسط اداره صمت.

    کالای اساسی حداکثر قیمت اتحادیه/صمت دارد و در apps.market بررسی می‌شود؛ اینجا قیمت را
    خود فروشگاه آزادانه می‌گذارد و فقط پس از تایید کارشناس صمت به مردم نمایش داده می‌شود.
    """
    union_section = "other_prices"

    queryset = ShopProduct.objects.select_related("store__union__chamber__county", "category", "reviewed_by")
    serializer_class = ShopProductSerializer
    read_roles = ("samt", "governorate", "chamber", "union")
    write_roles = ("samt",)
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "store", "category", "store__union", "is_special"]
    search_fields = ["name", "brand", "store__name"]
    ordering_fields = ["created_at", "price"]

    def _review(self, request, approve: bool):
        product = self.get_object()
        note = str(request.data.get("note") or "").strip()[:300]
        if not approve and not note:
            raise ValidationError({"note": "برای رد قیمت، دلیل را بنویسید."})
        if request.user.role not in SHOP_REVIEWER_ROLES:
            raise ValidationError({"detail": "تایید نرخ سایر کالاها بر عهده کارشناس اداره صمت است."})

        with transaction.atomic():
            product.status = ShopProduct.Status.APPROVED if approve else ShopProduct.Status.REJECTED
            product.reviewed_by = request.user
            product.reviewed_at = timezone.now()
            product.review_note = note
            product.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

        verb = "تایید شد و در صفحه فروشگاه نمایش داده می‌شود" if approve else "رد شد"
        notify([product.store.owner], f"قیمت «{product.name}» {verb}", note, "/panel/my-shop")
        return Response(self.get_serializer(product).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review(request, True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review(request, False)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        return Response({
            "pending": qs.filter(status=ShopProduct.Status.PENDING).count(),
            "approved": qs.filter(status=ShopProduct.Status.APPROVED).count(),
            "rejected": qs.filter(status=ShopProduct.Status.REJECTED).count(),
        })


class SpecialOfferSerializer(serializers.ModelSerializer):
    """کارت محصول تخفیف ویژه برای صفحه عمومی، همراه با مشخصات فروشگاه."""

    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    store = serializers.SerializerMethodField()

    class Meta:
        model = ShopProduct
        fields = ["id", "name", "description", "image", "brand", "price", "old_price", "discount_percent",
                  "unit_display", "is_available", "store"]

    def get_store(self, p):
        s = p.store
        return {"id": s.pk, "name": s.name, "address": s.address, "phone": s.phone,
                "lat": s.lat, "lng": s.lng}


@api_view(["GET"])
@permission_classes([AllowAny])
def public_special_offers(request):
    """«تخفیفات فروشگاه‌ها»: محصولات تخفیف ویژه تاییدشده، بیشترین تخفیف اول."""
    from django.db.models import ExpressionWrapper, F, FloatField

    from apps.core.pagination import Pagination

    qs = (
        ShopProduct.objects.filter(
            is_special=True, is_active=True, status=ShopProduct.Status.APPROVED,
            store__status=Store.Status.ACTIVE, old_price__gt=F("price"),
        )
        .select_related("store")
        .annotate(off=ExpressionWrapper((F("old_price") - F("price")) * 1.0 / F("old_price"), output_field=FloatField()))
    )
    if (county := request.query_params.get("county", "")).isdigit():
        qs = stores_in_county(qs, int(county), prefix="store__")
    if q := request.query_params.get("q"):
        qs = qs.filter(name__icontains=q[:80])
    ordering = {"price": "price", "recent": "-created_at"}.get(request.query_params.get("ordering"), "-off")
    paginator = Pagination()
    page = paginator.paginate_queryset(qs.order_by(ordering, "-created_at"), request)
    return paginator.get_paginated_response(SpecialOfferSerializer(page, many=True, context={"request": request}).data)


# ───────────────────────── فروشگاه ویژه و بسته‌های پیشنهادی ─────────────────────────


class BundleItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(source="product_id")
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)
    name = serializers.CharField(source="product.name", read_only=True)
    image = serializers.SerializerMethodField()
    price = serializers.IntegerField(source="product.price", read_only=True)
    list_price = serializers.SerializerMethodField()
    unit_display = serializers.CharField(source="product.get_unit_display", read_only=True)

    def get_list_price(self, it):
        return max(it.product.old_price or 0, it.product.price)

    def get_image(self, it):
        return it.product.image.url if it.product.image else None


class ShopBundleSerializer(serializers.ModelSerializer):
    items = BundleItemSerializer(many=True)
    items_total = serializers.SerializerMethodField()
    list_total = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    sold_out = serializers.SerializerMethodField()

    class Meta:
        model = ShopBundle
        fields = ["id", "store", "title", "description", "image", "price", "order", "is_active",
                  "items", "items_total", "list_total", "discount_percent", "sold_out"]
        read_only_fields = ["store"]

    def get_items_total(self, b):
        return sum(i.product.price * i.quantity for i in b.items.all())

    def get_list_total(self, b):
        return sum(max(i.product.old_price or 0, i.product.price) * i.quantity for i in b.items.all())

    def get_discount_percent(self, b):
        total = self.get_items_total(b)
        return round((total - b.price) / total * 100) if total > b.price else None

    def get_sold_out(self, b):
        return any(i.product.sold_out or not i.product.is_available or (
            i.product.stock is not None and i.product.stock < i.quantity) for i in b.items.all())

    def to_internal_value(self, data):
        # در درخواست multipart (همراه تصویر) اقلام به‌صورت رشته JSON می‌آید
        raw = data.get("items") if hasattr(data, "get") else None
        if isinstance(raw, str):
            try:
                data = {**{k: data.get(k) for k in data}, "items": json.loads(raw)}
            except ValueError:
                raise serializers.ValidationError({"items": "فهرست کالاهای بسته نامعتبر است."})
        return super().to_internal_value(data)

    def validate_price(self, v):
        if v < 1000:
            raise serializers.ValidationError("قیمت بسته باید دست‌کم ۱٬۰۰۰ ریال (۱۰۰ تومان) باشد.")
        return v

    def _check_items(self, items):
        store = self.context["store"]
        if not items:
            raise serializers.ValidationError({"items": "دست‌کم یک کالا به بسته اضافه کنید."})
        ids = [i["product_id"] for i in items]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError({"items": "یک کالا را فقط یک بار در بسته بیاورید."})
        found = set(ShopProduct.objects.filter(pk__in=ids, store=store).values_list("pk", flat=True))
        if set(ids) - found:
            raise serializers.ValidationError({"items": "همه کالاهای بسته باید از همین فروشگاه باشند."})

    def _set_items(self, bundle, items):
        bundle.items.all().delete()
        ShopBundleItem.objects.bulk_create(
            ShopBundleItem(bundle=bundle, product_id=i["product_id"], quantity=i.get("quantity", 1)) for i in items
        )

    def create(self, validated):
        items = validated.pop("items", [])
        self._check_items(items)
        with transaction.atomic():
            bundle = ShopBundle.objects.create(store=self.context["store"], **validated)
            self._set_items(bundle, items)
        return bundle

    def update(self, instance, validated):
        items = validated.pop("items", None)
        if items is not None:
            self._check_items(items)
        with transaction.atomic():
            for k, v in validated.items():
                setattr(instance, k, v)
            instance.save()
            if items is not None:
                self._set_items(instance, items)
        return instance


class ShopBundleViewSet(ScopedModelViewSet):
    """مدیریت بسته‌های پیشنهادی توسط فروشگاه."""

    queryset = ShopBundle.objects.select_related("store").prefetch_related("items__product")
    serializer_class = ShopBundleSerializer
    read_roles = ("admin", "store")
    write_roles = ("store",)
    pagination_class = None

    def _store(self):
        store = self.request.user.stores.first()
        if not store or store.status != Store.Status.ACTIVE:
            raise ValidationError({"detail": "فروشگاه فعالی برای شما ثبت نشده است."})
        return store

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method in ("POST", "PUT", "PATCH"):
            if self.kwargs.get("pk"):
                ctx["store"] = self.get_object().store
            elif self.request.user.role == Role.STORE:
                ctx["store"] = self._store()
            else:
                raise ValidationError({"detail": "بسته پیشنهادی را فقط مالک فروشگاه می‌سازد."})
        return ctx

    def perform_create(self, serializer):
        serializer.save()


@api_view(["GET"])
@permission_classes([AllowAny])
def public_featured_store(request):
    """فروشگاه ویژه‌ای که دکمه «طرح ویژه تخفیف» صفحه اصلی به آن می‌رود (نبودن = دکمه نمایش داده نشود)."""
    s = Store.objects.filter(is_featured=True, status=Store.Status.ACTIVE).order_by("-created_at").first()
    if not s:
        return Response(None)
    return Response({"id": s.pk, "name": s.name})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_bundles(request, pk):
    store = get_object_or_404(Store, pk=pk, status=Store.Status.ACTIVE)
    qs = store.bundles.filter(is_active=True).prefetch_related("items__product")
    # بسته‌ای که یکی از کالاهایش دیگر عرضه نمی‌شود، نمایش داده نمی‌شود
    rows = [b for b in qs if all(i.product.is_public for i in b.items.all())]
    return Response(ShopBundleSerializer(rows, many=True, context={"request": request}).data)
