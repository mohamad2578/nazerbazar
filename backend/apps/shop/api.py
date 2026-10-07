from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import role_permission
from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store

from .models import ShopCategory, ShopProduct


class ShopCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopCategory
        fields = ["id", "name", "icon", "order"]


class ShopProductSerializer(serializers.ModelSerializer):
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    store_name = serializers.CharField(source="store.name", read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShopProduct
        fields = [
            "id", "store", "store_name", "category", "category_name", "name", "description", "image",
            "price", "old_price", "discount_percent", "unit", "unit_display", "brand",
            "is_available", "is_active", "order", "created_at",
        ]
        read_only_fields = ["store"]


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
        self._save_in_scope(serializer, store=self._my_store())

    def perform_update(self, serializer):
        serializer.validated_data.pop("store", None)
        self._save_in_scope(serializer)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_shop(request, pk):
    """ویترین فروشگاه اینترنتی یک فروشگاه برای نمایش عمومی."""
    store = get_object_or_404(Store, pk=pk, status=Store.Status.ACTIVE)
    qs = store.shop_products.filter(is_active=True).select_related("category")
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
        is_active=True, is_available=True, store__status=Store.Status.ACTIVE
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
        "available": qs.filter(is_active=True, is_available=True).count(),
        "hidden": qs.filter(is_active=False).count(),
    })
