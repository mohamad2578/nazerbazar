from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store, Union

from . import services
from .models import Allocation, AllocationShare, Quota


class QuotaSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_address = serializers.CharField(source="store.address", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    commodity_name = serializers.CharField(source="share.allocation.commodity.name", read_only=True)
    allocation_title = serializers.CharField(source="share.allocation.title", read_only=True)
    unit = serializers.CharField(source="share.allocation.unit", read_only=True)
    consumer_price = serializers.IntegerField(source="share.allocation.consumer_price", read_only=True)
    remaining = serializers.FloatField(read_only=True)
    events = serializers.SerializerMethodField()

    class Meta:
        model = Quota
        fields = [
            "id", "share", "store", "store_name", "store_address", "tracking_code", "quantity",
            "received_quantity", "sold_quantity", "remaining", "carrier", "status", "status_display",
            "commodity_name", "allocation_title", "unit", "consumer_price", "created_at", "events",
        ]
        read_only_fields = ["tracking_code", "received_quantity", "sold_quantity", "status"]

    def get_events(self, q):
        return [
            {"status": e.status, "status_display": e.get_status_display(), "note": e.note, "created_at": e.created_at}
            for e in q.events.all()
        ]


class ShareSerializer(serializers.ModelSerializer):
    union_name = serializers.CharField(source="union.name", read_only=True)
    allocation_title = serializers.CharField(source="allocation.title", read_only=True)
    commodity_name = serializers.CharField(source="allocation.commodity.name", read_only=True)
    unit = serializers.CharField(source="allocation.unit", read_only=True)
    allocation_status = serializers.CharField(source="allocation.status", read_only=True)
    consumer_price = serializers.IntegerField(source="allocation.consumer_price", read_only=True)
    assigned = serializers.SerializerMethodField()
    received = serializers.SerializerMethodField()

    class Meta:
        model = AllocationShare
        fields = [
            "id", "allocation", "allocation_title", "commodity_name", "unit", "allocation_status",
            "consumer_price", "union", "union_name", "quantity", "assigned", "received",
        ]

    def _active(self, s):
        return s.quotas.exclude(status=Quota.Status.CANCELED)

    def get_assigned(self, s):
        return float(self._active(s).aggregate(v=Sum("quantity"))["v"] or 0)

    def get_received(self, s):
        return float(self._active(s).aggregate(v=Sum("received_quantity"))["v"] or 0)


class AllocationSerializer(serializers.ModelSerializer):
    commodity_name = serializers.CharField(source="commodity.name", read_only=True)
    province_name = serializers.CharField(source="province.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shares = ShareSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Allocation
        exclude = ["created_by"]
        extra_kwargs = {"province": {"required": False}}

    def get_progress(self, a):
        q = Quota.objects.filter(share__allocation=a).exclude(status=Quota.Status.CANCELED).aggregate(
            assigned=Sum("quantity"), received=Sum("received_quantity"), sold=Sum("sold_quantity")
        )
        total = float(a.total_quantity)
        shared = float(a.shares.aggregate(v=Sum("quantity"))["v"] or 0)
        received = float(q["received"] or 0)
        return {
            "total": total, "shared": shared, "assigned": float(q["assigned"] or 0),
            "received": received, "sold": float(q["sold"] or 0),
            # نشتی = آنچه تخصیص یافته ولی به فروشگاه نرسیده (برای سهمیه‌های ارسال‌شده)
            "gap": round(float(q["assigned"] or 0) - received, 2),
            "price_gap_percent": round((a.consumer_price - a.allocation_price) / a.allocation_price * 100, 1)
            if a.allocation_price else None,
        }


class AllocationViewSet(ScopedModelViewSet):
    queryset = Allocation.objects.select_related("commodity", "province").prefetch_related("shares__union")
    serializer_class = AllocationSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    write_roles = ("governorate", "samt")
    filterset_fields = ["status", "commodity", "province"]
    search_fields = ["title", "supplier"]

    def perform_create(self, serializer):
        u = self.request.user
        extra = {"created_by": u}
        if u.role == Role.GOVERNORATE:
            extra["province"] = u.province
        elif not serializer.validated_data.get("province"):
            raise ValidationError({"province": "استان را انتخاب کنید."})
        self._save_in_scope(serializer, **extra)

    @action(detail=True, methods=["post"])
    def set_share(self, request, pk=None):
        a = self.get_object()
        if request.user.role not in (Role.GOVERNORATE, Role.ADMIN):
            raise ValidationError({"detail": "فقط استانداری سهم اتحادیه‌ها را تعیین می‌کند."})
        union = get_object_or_404(Union, pk=request.data.get("union"))
        services.set_share(a, union, request.data.get("quantity"))
        return Response(AllocationSerializer(self.get_queryset().get(pk=a.pk)).data)


class ShareViewSet(ScopedModelViewSet):
    """سهم اتحادیه از تخصیص و تقسیم آن بین فروشگاه‌ها"""

    queryset = AllocationShare.objects.select_related("allocation__commodity", "union")
    serializer_class = ShareSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    write_roles = ("union",)
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["allocation", "union"]

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "سهم‌ها از صفحه تخصیص تعیین می‌شوند."})

    @action(detail=True)
    def suggest(self, request, pk=None):
        return Response(services.suggest_split(self.get_object()))

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        share = self.get_object()
        items = request.data.get("items") or [request.data]
        created = []
        for it in items:
            if not it.get("quantity") or float(it["quantity"]) <= 0:
                continue
            store = get_object_or_404(Store, pk=it.get("store"))
            created.append(services.assign_quota(share, store, it["quantity"], request.user, it.get("carrier", "")))
        return Response(QuotaSerializer(created, many=True).data, status=201)


class QuotaViewSet(ScopedModelViewSet):
    queryset = Quota.objects.select_related("store", "share__allocation__commodity").prefetch_related("events")
    serializer_class = QuotaSerializer
    read_roles = ("governorate", "samt", "chamber", "union", "store")
    write_roles = ("union", "store")
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "store", "share", "share__allocation"]
    search_fields = ["tracking_code", "store__name"]

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "سهمیه از طریق سهم اتحادیه تخصیص داده می‌شود."})

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
        q = self.get_object()
        new = request.data.get("status")
        role = request.user.role
        # ارسال/لغو با اتحادیه، تایید تحویل و گزارش فروش با فروشگاه
        allowed = {
            Role.UNION: {Quota.Status.DISPATCHED, Quota.Status.CANCELED},
            Role.STORE: {Quota.Status.RECEIVED, Quota.Status.SOLD_OUT},
        }.get(role, set(Quota.Status.values) if role == Role.ADMIN else set())
        if new not in allowed:
            raise ValidationError({"status": "این اقدام در اختیار شما نیست."})
        services.advance_quota(
            q, new, request.user, request.data.get("received_quantity"), request.data.get("sold_quantity"),
            request.data.get("note", ""),
        )
        return Response(QuotaSerializer(q).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_subsidized(request):
    """فروشگاه‌هایی که کالای تخصیصی/یارانه‌ای موجود دارند (شفافیت توزیع برای شهروند)"""
    qs = Quota.objects.filter(
        status=Quota.Status.RECEIVED, share__allocation__status=Allocation.Status.ACTIVE, store__status=Store.Status.ACTIVE
    ).select_related("store", "share__allocation__commodity")
    if county := request.query_params.get("county"):
        qs = qs.filter(store__union__chamber__county_id=county)
    if commodity := request.query_params.get("commodity"):
        qs = qs.filter(share__allocation__commodity_id=commodity)
    rows = []
    for q in qs:
        if q.remaining <= 0:
            continue
        a = q.share.allocation
        rows.append({
            "tracking_code": q.tracking_code, "commodity": a.commodity.name, "allocation": a.title,
            "consumer_price": a.consumer_price, "unit": a.unit, "remaining": q.remaining,
            "store": {"id": q.store_id, "name": q.store.name, "address": q.store.address, "phone": q.store.phone,
                      "lat": q.store.lat, "lng": q.store.lng},
        })
    return Response(rows)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_track_quota(request, code):
    """رهگیری عمومی محموله با کد درج‌شده روی بسته/فاکتور"""
    q = get_object_or_404(Quota.objects.select_related("store", "share__allocation__commodity"), tracking_code=code.upper())
    a = q.share.allocation
    return Response({
        "tracking_code": q.tracking_code, "commodity": a.commodity.name, "allocation": a.title,
        "supplier": a.supplier, "consumer_price": a.consumer_price, "unit": a.unit, "store_name": q.store.name,
        "store_address": q.store.address, "status_display": q.get_status_display(),
        "events": [{"status_display": e.get_status_display(), "note": e.note, "created_at": e.created_at} for e in q.events.all()],
    })
