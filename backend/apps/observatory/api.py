from django.db.models import Avg, Max, Min, Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response

from apps.core.permissions import role_permission
from apps.core.scoping import scope_filter
from apps.core.views import ScopedModelViewSet
from apps.market.services import visible_offers

from . import services
from .models import Alert, Commodity, CommodityReport


class CommoditySerializer(serializers.ModelSerializer):
    group_display = serializers.CharField(source="get_group_display", read_only=True)

    class Meta:
        model = Commodity
        fields = ["id", "name", "group", "group_display", "unit", "subsidized", "basket_monthly_qty", "order"]


class CommodityReportSerializer(serializers.ModelSerializer):
    commodity_name = serializers.CharField(source="commodity.name", read_only=True)
    province_name = serializers.CharField(source="province.name", read_only=True, default="کل کشور")
    landed_cost = serializers.IntegerField(read_only=True)
    per_capita_supply = serializers.FloatField(read_only=True)
    supply_gap_kt = serializers.FloatField(read_only=True)
    chain_markup_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = CommodityReport
        exclude = ["created_by", "created_at", "updated_at"]


class AlertSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    county_name = serializers.CharField(source="county.name", read_only=True, default="")
    product_name = serializers.CharField(source="product.name", read_only=True, default="")

    class Meta:
        model = Alert
        exclude = ["dedupe_key"]


class CommodityViewSet(viewsets.ModelViewSet):
    queryset = Commodity.objects.all()
    serializer_class = CommoditySerializer
    pagination_class = None
    filterset_fields = ["group", "subsidized"]
    search_fields = ["name"]

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [role_permission("admin")()]


class CommodityReportViewSet(ScopedModelViewSet):
    """ورود داده جدول‌های الف و ب (نیاز/تامین/قیمت زنجیره) — استانداری و مدیر کل"""

    queryset = CommodityReport.objects.select_related("commodity", "province")
    serializer_class = CommodityReportSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    write_roles = ("governorate", "samt")
    filterset_fields = ["commodity", "province", "period"]
    ordering_fields = ["period"]

    def get_queryset(self):
        f = scope_filter(self.request.user, CommodityReport.SCOPE)
        if self.request.method in SAFE_METHODS:
            f |= Q(province__isnull=True)  # گزارش‌های ملی برای همه نقش‌های پنل قابل مشاهده است
        return self.queryset.filter(f)

    def perform_create(self, serializer):
        u = self.request.user
        extra = {"created_by": u}
        if u.role == "governorate":
            extra["province"] = u.province
        self._save_in_scope(serializer, **extra)


class AlertViewSet(ScopedModelViewSet):
    queryset = Alert.objects.select_related("county", "product", "store")
    serializer_class = AlertSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    write_roles = ("governorate", "samt", "chamber", "union")
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["kind", "level", "is_resolved", "county"]

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        a = self.get_object()
        a.is_resolved = True
        a.save(update_fields=["is_resolved"])
        return Response(AlertSerializer(a).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_observatory(request):
    """نمای عمومی رصدخانه: قیمت زنده کالاهای اساسی از فروشگاه‌ها + آخرین گزارش زنجیره قیمت"""
    county = request.query_params.get("county")
    offers = visible_offers().filter(product__commodity__isnull=False)
    if county:
        offers = offers.filter(store__union__chamber__county_id=county)
    live = {
        r["product__commodity"]: r
        for r in offers.values("product__commodity").annotate(mn=Min("price"), av=Avg("price"), mx=Max("price"))
    }
    latest = {}
    for r in CommodityReport.objects.filter(province__isnull=True).select_related("commodity").order_by("-period"):
        latest.setdefault(r.commodity_id, r)
    rows = []
    for c in Commodity.objects.exclude(group=Commodity.Group.FEED):
        lv, rep = live.get(c.pk), latest.get(c.pk)
        rows.append({
            "id": c.pk, "name": c.name, "group": c.get_group_display(), "unit": c.unit, "subsidized": c.subsidized,
            "live_min": lv and lv["mn"], "live_avg": lv and round(lv["av"]), "live_max": lv and lv["mx"],
            "report": CommodityReportSerializer(rep).data if rep else None,
        })
    return Response({"items": rows, "basket": services.basket_cost([county] if county else None)})
