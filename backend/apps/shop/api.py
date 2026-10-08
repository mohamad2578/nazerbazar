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
from apps.orgs.models import Store

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
    union_name = serializers.CharField(source="store.union.name", read_only=True)

    class Meta:
        model = ShopProduct
        fields = [
            "id", "store", "store_name", "union_name", "category", "category_name", "name", "description", "image",
            "price", "old_price", "discount_percent", "unit", "unit_display", "brand",
            "is_available", "is_active", "order", "created_at",
            "status", "status_display", "reviewed_at", "review_note",
        ]
        read_only_fields = ["store", "status", "reviewed_at", "review_note"]


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
    filterset_fields = ["category", "is_active", "is_available", "store"]
    search_fields = ["name", "brand", "description"]

    def _my_store(self) -> Store:
        store = self.request.user.stores.first()
        if not store:
            raise ValidationError({"detail": "ابتدا فروشگاه خود را ثبت کنید."})
        if store.status != Store.Status.ACTIVE:
            raise ValidationError({"detail": "فروشگاه شما هنوز فعال نشده است."})
        return store

    def perform_create(self, serializer):
        product = self._save_in_scope(serializer, store=self._my_store(),
                                      status=ShopProduct.Status.PENDING)
        self._notify_reviewers(product, "محصول جدید در انتظار تایید")

    def perform_update(self, serializer):
        serializer.validated_data.pop("store", None)
        # ویرایش نام یا قیمت، محصول را دوباره به صف تایید کارشناس صمت می‌برد
        instance = serializer.instance
        changed = any(
            f in serializer.validated_data and serializer.validated_data[f] != getattr(instance, f)
            for f in REVIEWABLE_FIELDS
        )
        extra = {"status": ShopProduct.Status.PENDING, "reviewed_at": None, "review_note": ""} if changed else {}
        product = self._save_in_scope(serializer, **extra)
        if changed:
            self._notify_reviewers(product, "تغییر قیمت/مشخصات محصول در انتظار تایید")

    def _notify_reviewers(self, product: ShopProduct, title: str) -> None:
        from apps.accounts.models import User

        province = product.store.union.chamber.county.province_id
        reviewers = User.objects.filter(role=Role.SAMT, province_id=province)
        notify(reviewers, title,
               f"«{product.name}» از فروشگاه {product.store.name} — {product.price:,} ریال",
               "/panel/other-prices")


@api_view(["GET"])
@permission_classes([AllowAny])
def public_shop(request, pk):
    """ویترین فروشگاه اینترنتی یک فروشگاه برای نمایش عمومی."""
    store = get_object_or_404(Store, pk=pk, status=Store.Status.ACTIVE)
    qs = store.shop_products.filter(
        is_active=True, status=ShopProduct.Status.APPROVED
    ).select_related("category")
    if category := request.query_params.get("category"):
        qs = qs.filter(category_id=category)
    if q := request.query_params.get("q"):
        qs = qs.filter(name__icontains=q)
    return Response(ShopProductSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_shop_products(request):
    """جستجوی محصولات فروشگاهی در میان همه فروشگاه‌های فعال (ویترین سراسری)."""
    from apps.core.pagination import Pagination

    qs = ShopProduct.objects.filter(
        is_active=True, is_available=True, status=ShopProduct.Status.APPROVED,
        store__status=Store.Status.ACTIVE,
    ).select_related("store", "category")
    if county := request.query_params.get("county"):
        qs = qs.filter(store__union__chamber__county_id=county)
    if category := request.query_params.get("category"):
        qs = qs.filter(category_id=category)
    if q := request.query_params.get("q"):
        qs = qs.filter(name__icontains=q)
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

    کالای اساسی نرخ مصوب اتحادیه/صمت دارد و در apps.market بررسی می‌شود؛ اینجا قیمت را
    خود فروشگاه آزادانه می‌گذارد و فقط پس از تایید کارشناس صمت به مردم نمایش داده می‌شود.
    """

    queryset = ShopProduct.objects.select_related("store__union__chamber__county", "category", "reviewed_by")
    serializer_class = ShopProductSerializer
    read_roles = ("samt", "governorate", "chamber", "union")
    write_roles = ("samt",)
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "store", "category", "store__union"]
    search_fields = ["name", "brand", "store__name"]
    ordering_fields = ["created_at", "price"]

    def _review(self, request, approve: bool):
        product = self.get_object()
        note = (request.data.get("note") or "").strip()
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
