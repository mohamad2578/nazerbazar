from django.db import transaction
from django.db.models import Avg, Count, Min, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.permissions import role_permission
from apps.core.utils import haversine_km
from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store

from . import services
from .models import Category, OfficialPrice, Product, Review, StoreOffer


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon", "order"]


class ProductSerializer(serializers.ModelSerializer):
    union_name = serializers.CharField(source="union.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    commodity_name = serializers.CharField(source="commodity.name", read_only=True, default="")
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    min_allowed_price = serializers.IntegerField(read_only=True)
    initial_price = serializers.IntegerField(write_only=True, required=False, min_value=1)
    offers_count = serializers.IntegerField(read_only=True, default=0)
    stale_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Product
        fields = [
            "id", "union", "union_name", "category", "category_name", "commodity", "commodity_name", "name",
            "unit", "unit_display", "unit_amount", "description", "image", "current_price", "max_discount_percent",
            "min_allowed_price", "price_changed_at", "is_active", "initial_price", "offers_count", "stale_count",
        ]
        read_only_fields = ["current_price", "price_changed_at"]
        extra_kwargs = {"union": {"required": False}}


class OfficialPriceSerializer(serializers.ModelSerializer):
    set_by_name = serializers.CharField(source="set_by.full_name", read_only=True, default="")

    class Meta:
        model = OfficialPrice
        fields = ["id", "price", "previous_price", "max_discount_percent", "note", "set_by_name", "created_at"]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [role_permission("admin")()]


class ProductViewSet(ScopedModelViewSet):
    """تعریف کالا و نرخ‌گذاری توسط اتحادیه"""

    serializer_class = ProductSerializer
    read_roles = ("governorate", "chamber", "union")
    write_roles = ("union",)
    filterset_fields = ["union", "category", "commodity", "is_active", "union__chamber"]
    search_fields = ["name"]
    ordering_fields = ["name", "current_price", "price_changed_at"]

    queryset = Product.objects.select_related("union", "category", "commodity")

    def get_queryset(self):
        from django.db.models import F

        return super().get_queryset().annotate(
            offers_count=Count("offers", distinct=True),
            stale_count=Count("offers", filter=Q(offers__confirmed_at__lt=F("price_changed_at")), distinct=True),
        )

    def perform_create(self, serializer):
        u = self.request.user
        initial = serializer.validated_data.pop("initial_price", None)
        extra = {"union": u.union} if u.role == Role.UNION else {}
        if not extra and not serializer.validated_data.get("union"):
            raise ValidationError({"union": "اتحادیه را انتخاب کنید."})
        with transaction.atomic():
            product = self._save_in_scope(serializer, **extra)
            if initial:
                services.set_official_price(product, initial, u)

    def perform_update(self, serializer):
        serializer.validated_data.pop("initial_price", None)
        serializer.validated_data.pop("union", None)
        self._save_in_scope(serializer)

    def perform_destroy(self, instance):
        # کالای دارای سابقه حذف نمی‌شود، غیرفعال می‌شود
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"])
    def set_price(self, request, pk=None):
        product = self.get_object()
        if request.user.role not in (Role.UNION, Role.ADMIN):
            raise ValidationError({"detail": "فقط اتحادیه نرخ تعیین می‌کند."})
        try:
            price = int(request.data.get("price"))
        except (TypeError, ValueError):
            raise ValidationError({"price": "نرخ را به ریال وارد کنید."})
        services.set_official_price(
            product, price, request.user, request.data.get("max_discount_percent"), request.data.get("note", "")
        )
        product.refresh_from_db()
        return Response(ProductSerializer(product, context={"request": request}).data)

    @action(detail=True)
    def history(self, request, pk=None):
        product = self.get_object()
        return Response(OfficialPriceSerializer(product.price_history.all()[:100], many=True).data)

    @action(detail=True)
    def offers(self, request, pk=None):
        product = self.get_object()
        qs = product.offers.select_related("store")
        return Response([
            {"store": o.store_id, "store_name": o.store.name, "price": o.price, "is_available": o.is_available,
             "confirmed_at": o.confirmed_at, "is_stale": o.is_stale, "store_status": o.store.status}
            for o in qs.order_by("price")
        ])


# ───────────────────────── پنل فروشگاه ─────────────────────────


def _my_store(user) -> Store:
    store = user.stores.select_related("union").first()
    if not store:
        raise ValidationError({"detail": "ابتدا فروشگاه خود را ثبت کنید."})
    return store


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_catalog(request):
    """کالاهای اتحادیه به همراه قیمت فعلی این فروشگاه"""
    store = _my_store(request.user)
    offers = {o.product_id: o for o in store.offers.all()}
    now = timezone.now()
    grace = services.grace_period()
    rows = []
    for p in Product.objects.filter(union=store.union, is_active=True).select_related("category").order_by("name"):
        o = offers.get(p.pk)
        stale = bool(o and p.price_changed_at and o.confirmed_at < p.price_changed_at)
        rows.append({
            "product": p.pk, "name": p.name, "unit_display": p.get_unit_display(),
            "category_name": p.category.name if p.category else "", "image": p.image.url if p.image else None,
            "official_price": p.current_price, "min_allowed_price": p.min_allowed_price,
            "max_discount_percent": p.max_discount_percent, "price_changed_at": p.price_changed_at,
            "offer_price": o.price if o else None, "is_available": o.is_available if o else None,
            "confirmed_at": o.confirmed_at if o else None, "is_stale": stale,
            "deadline": (p.price_changed_at + grace) if stale else None,
            "hidden": bool(stale and p.price_changed_at + grace < now),
        })
    return Response({"store": {"id": store.pk, "name": store.name, "status": store.status}, "items": rows})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def store_save_offers(request):
    """ثبت گروهی قیمت‌ها: [{product, price, is_available}]؛ خطاها به تفکیک کالا برمی‌گردد."""
    store = _my_store(request.user)
    items = request.data if isinstance(request.data, list) else request.data.get("items", [])
    saved, errors = [], {}
    for item in items:
        pid = item.get("product")
        product = Product.objects.filter(pk=pid).first()
        if not product:
            errors[str(pid)] = "کالا یافت نشد."
            continue
        try:
            with transaction.atomic():
                services.upsert_offer(store, product, item.get("price"), bool(item.get("is_available", True)))
            saved.append(pid)
        except Exception as e:  # noqa: BLE001 - پیام خطای اعتبارسنجی به کاربر نمایش داده می‌شود
            msg = getattr(e, "message_dict", None) or {"price": [str(e)]}
            errors[str(pid)] = " ".join(sum(msg.values(), [])) if isinstance(msg, dict) else str(msg)
    return Response({"saved": saved, "errors": errors}, status=200 if not errors else 207)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def store_remove_offer(request, product_id):
    store = _my_store(request.user)
    store.offers.filter(product_id=product_id).delete()
    return Response(status=204)


# ───────────────────────── سایت عمومی ─────────────────────────


def _public_products(params):
    visible = services.visible_offers()
    qs = Product.objects.filter(is_active=True, current_price__gt=0, union__is_active=True).select_related(
        "union__chamber__county", "category"
    )
    if county := params.get("county"):
        qs = qs.filter(union__chamber__county_id=county)
    if union := params.get("union"):
        qs = qs.filter(union_id=union)
    if cat := params.get("category"):
        qs = qs.filter(category_id=cat)
    if commodity := params.get("commodity"):
        qs = qs.filter(commodity_id=commodity)
    if q := params.get("q"):
        qs = qs.filter(Q(name__icontains=q) | Q(union__name__icontains=q))
    stats = visible.filter(product=OuterRef("pk")).values("product")
    return qs.annotate(
        offers_count=Subquery(stats.annotate(c=Count("pk")).values("c")[:1]),
        min_price=Subquery(stats.annotate(m=Min("price")).values("m")[:1]),
    )


def _product_card(p, request):
    return {
        "id": p.pk, "name": p.name, "unit_display": p.get_unit_display(), "unit_amount": p.unit_amount,
        "image": request.build_absolute_uri(p.image.url) if p.image else None,
        "union": p.union_id, "union_name": p.union.name, "county_name": p.union.chamber.county.name,
        "category": p.category_id, "category_name": p.category.name if p.category else "",
        "official_price": p.current_price, "min_allowed_price": p.min_allowed_price,
        "price_changed_at": p.price_changed_at,
        "offers_count": getattr(p, "offers_count", None) or 0, "min_price": getattr(p, "min_price", None),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def public_products(request):
    from apps.core.pagination import Pagination

    qs = _public_products(request.query_params)
    ordering = {"price": "current_price", "-price": "-current_price", "recent": "-price_changed_at"}.get(
        request.query_params.get("ordering"), "name"
    )
    paginator = Pagination()
    page = paginator.paginate_queryset(qs.order_by(ordering), request)
    return paginator.get_paginated_response([_product_card(p, request) for p in page])


def _offer_row(o, request, lat=None, lng=None, now=None):
    s = o.store
    row = {
        "id": o.pk, "price": o.price, "discount_percent": o.discount_percent, "confirmed_at": o.confirmed_at,
        "pending_update": o.is_stale,  # در مهلت ۲۴ ساعته هنوز به‌روز نشده
        "store": {
            "id": s.pk, "name": s.name, "address": s.address, "phone": s.phone, "lat": s.lat, "lng": s.lng,
            "working_hours": s.working_hours, "is_verified": s.is_verified,
            "rating_avg": s.rating_avg, "rating_count": s.rating_count,
            "photo": request.build_absolute_uri(s.photo.url) if s.photo else None,
        },
        "distance_km": None,
    }
    if lat and lng and s.lat is not None and s.lng is not None:
        row["distance_km"] = round(haversine_km(lat, lng, s.lat, s.lng), 2)
    return row


@api_view(["GET"])
@permission_classes([AllowAny])
def public_product_detail(request, pk):
    p = get_object_or_404(
        Product.objects.select_related("union__chamber__county", "category"), pk=pk, is_active=True
    )
    lat, lng = request.query_params.get("lat"), request.query_params.get("lng")
    offers = services.visible_offers().filter(product=p).select_related("store", "product")
    rows = [_offer_row(o, request, lat, lng) for o in offers]
    # مرتب‌سازی: کمترین قیمت، سپس نزدیک‌ترین، سپس امتیاز بالاتر
    rows.sort(key=lambda r: (r["price"], r["distance_km"] if r["distance_km"] is not None else 1e9, -float(r["store"]["rating_avg"])))
    if request.query_params.get("sort") == "distance" and lat:
        rows.sort(key=lambda r: (r["distance_km"] if r["distance_km"] is not None else 1e9, r["price"]))
    history = list(p.price_history.values("price", "created_at")[:30])[::-1]
    card = _product_card(p, request)
    card.update({
        "description": p.description, "max_discount_percent": p.max_discount_percent,
        "union_phone": p.union.phone, "offers": rows, "history": history,
        "offers_count": len(rows), "min_price": rows[0]["price"] if rows else None,
        "avg_price": round(sum(r["price"] for r in rows) / len(rows)) if rows else None,
    })
    return Response(card)


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "comment", "user_name", "created_at"]

    def get_user_name(self, r):
        name = r.user.first_name or "کاربر"
        return f"{name} {r.user.last_name[:1]}." if r.user.last_name else name


@api_view(["GET"])
@permission_classes([AllowAny])
def public_store_detail(request, pk):
    s = get_object_or_404(Store.objects.select_related("union__chamber__county"), pk=pk, status=Store.Status.ACTIVE)
    offers = services.visible_offers().filter(store=s).select_related("product", "store").order_by("product__name")
    return Response({
        "id": s.pk, "name": s.name, "address": s.address, "phone": s.phone, "lat": s.lat, "lng": s.lng,
        "working_hours": s.working_hours, "is_verified": s.is_verified, "rating_avg": s.rating_avg,
        "rating_count": s.rating_count, "union_name": s.union.name, "county_name": s.union.chamber.county.name,
        "photo": request.build_absolute_uri(s.photo.url) if s.photo else None,
        "offers": [
            {"product": o.product_id, "name": o.product.name, "unit_display": o.product.get_unit_display(),
             "price": o.price, "official_price": o.product.current_price, "discount_percent": o.discount_percent,
             "pending_update": o.is_stale}
            for o in offers
        ],
        "reviews": ReviewSerializer(s.reviews.filter(is_visible=True).select_related("user")[:30], many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_review(request, pk):
    store = get_object_or_404(Store, pk=pk, status=Store.Status.ACTIVE)
    if store.owner_id == request.user.pk:
        raise ValidationError({"detail": "امکان ثبت نظر برای فروشگاه خودتان وجود ندارد."})
    s = ReviewSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    with transaction.atomic():
        Review.objects.update_or_create(store=store, user=request.user, defaults=s.validated_data)
        agg = store.reviews.filter(is_visible=True).aggregate(a=Avg("rating"), c=Count("pk"))
        store.rating_avg, store.rating_count = round(agg["a"] or 0, 2), agg["c"]
        store.save(update_fields=["rating_avg", "rating_count"])
    return Response({"rating_avg": store.rating_avg, "rating_count": store.rating_count})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_stats(request):
    from apps.complaints.models import Complaint

    county = request.query_params.get("county")
    stores = Store.objects.filter(status=Store.Status.ACTIVE)
    products = Product.objects.filter(is_active=True, current_price__gt=0)
    if county:
        stores = stores.filter(union__chamber__county_id=county)
        products = products.filter(union__chamber__county_id=county)
    recent = products.filter(price_changed_at__isnull=False).order_by("-price_changed_at").select_related(
        "union__chamber__county", "category"
    )[:8]
    latest_changes = []
    for p in recent:
        last = p.price_history.first()
        card = _product_card(p, request)
        card["previous_price"] = last.previous_price if last else None
        latest_changes.append(card)
    return Response({
        "stores": stores.count(),
        "products": products.count(),
        "unions": products.values("union").distinct().count(),
        "resolved_complaints": Complaint.objects.filter(status=Complaint.Status.RESOLVED).count(),
        "latest_changes": latest_changes,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def public_map(request):
    """نقشه فروشگاه‌های فعال (برای نمای نقشه در سایت)"""
    qs = Store.objects.filter(status=Store.Status.ACTIVE, lat__isnull=False).select_related("union")
    if county := request.query_params.get("county"):
        qs = qs.filter(union__chamber__county_id=county)
    if union := request.query_params.get("union"):
        qs = qs.filter(union_id=union)
    return Response([
        {"id": s.pk, "name": s.name, "lat": s.lat, "lng": s.lng, "union_name": s.union.name,
         "rating_avg": s.rating_avg, "is_verified": s.is_verified}
        for s in qs[:2000]
    ])
