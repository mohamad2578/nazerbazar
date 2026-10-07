from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.models import Role
from apps.core.utils import normalize_mobile
from apps.core.views import ScopedModelViewSet

from . import services
from .models import Complaint, ComplaintEvent


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ComplaintEvent
        fields = ["id", "status", "status_display", "note", "actor_name", "is_public", "created_at"]

    def get_actor_name(self, e):
        if not e.actor:
            return ""
        return e.actor.get_role_display() if e.actor.role != Role.CITIZEN else "شهروند"


class ComplaintSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True, default="")
    store_address = serializers.CharField(source="store.address", read_only=True, default="")
    store_phone = serializers.CharField(source="store.phone", read_only=True, default="")
    product_name = serializers.CharField(source="product.name", read_only=True, default="")
    union_name = serializers.CharField(source="union.name", read_only=True, default="")
    chamber_name = serializers.CharField(source="chamber.name", read_only=True)
    reporter_mobile = serializers.CharField(source="reporter.mobile", read_only=True)
    events = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            "id", "tracking_code", "kind", "kind_display", "status", "status_display", "store", "store_name",
            "store_address", "store_phone", "product", "product_name", "union", "union_name", "chamber",
            "chamber_name", "shop_name", "shop_address", "announced_price", "official_price", "paid_price",
            "description", "attachment", "lat", "lng", "reporter_name", "reporter_mobile",
            "violation_confirmed", "resolution", "resolved_at", "created_at", "events",
        ]
        read_only_fields = [
            "tracking_code", "status", "union", "announced_price", "official_price", "violation_confirmed",
            "resolution", "resolved_at", "created_at",
        ]
        extra_kwargs = {"chamber": {"required": False}, "reporter_name": {"required": False}}

    def get_events(self, c):
        qs = c.events.select_related("actor")
        req = self.context.get("request")
        if not req or req.user.role in (Role.CITIZEN,) or getattr(self, "_public", False):
            qs = qs.filter(is_public=True)
        return EventSerializer(qs, many=True).data


class PublicComplaintSerializer(ComplaintSerializer):
    """نمای شهروند: اطلاعات تماس گزارش‌دهنده نمایش داده نمی‌شود"""

    class Meta(ComplaintSerializer.Meta):
        fields = [f for f in ComplaintSerializer.Meta.fields if f not in ("reporter_mobile",)]


class StoreComplaintSerializer(ComplaintSerializer):
    """نمای فروشگاه: هویت گزارش‌دهنده محرمانه است"""

    _public = True

    class Meta(ComplaintSerializer.Meta):
        fields = [f for f in ComplaintSerializer.Meta.fields if f not in ("reporter_mobile", "reporter_name", "lat", "lng")]


class ComplaintThrottle(UserRateThrottle):
    scope = "complaint"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ComplaintThrottle])
def submit(request):
    s = ComplaintSerializer(data=request.data, context={"request": request})
    s.is_valid(raise_exception=True)
    data = dict(s.validated_data)
    if not data.get("reporter_name"):
        data["reporter_name"] = request.user.full_name or "شهروند"
    c = services.submit_complaint(request.user, data)
    return Response(PublicComplaintSerializer(c, context={"request": request}).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_complaints(request):
    qs = Complaint.objects.filter(reporter=request.user).select_related("store", "product", "union", "chamber")
    return Response(PublicComplaintSerializer(qs[:50], many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def track(request):
    """پیگیری با کد رهگیری + موبایل ثبت‌کننده (بدون نیاز به ورود)"""
    code = (request.query_params.get("code") or "").strip().upper()
    try:
        mobile = normalize_mobile(request.query_params.get("mobile", ""))
    except Exception:  # noqa: BLE001
        raise ValidationError({"mobile": "شماره موبایل معتبر نیست."})
    c = get_object_or_404(Complaint, tracking_code=code, reporter__mobile=mobile)
    s = PublicComplaintSerializer(c)
    s._public = True
    return Response(s.data)


class ComplaintViewSet(ScopedModelViewSet):
    """کارتابل شکایات: اتحادیه رسیدگی می‌کند، اتاق اصناف رونوشت دارد و نظارت/ارجاع می‌کند"""

    queryset = Complaint.objects.select_related("store", "product", "union", "chamber", "reporter")
    serializer_class = ComplaintSerializer
    read_roles = ("governorate", "samt", "chamber", "union", "store")
    write_roles = ("chamber", "samt", "union")
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "kind", "union", "chamber", "store", "violation_confirmed"]
    search_fields = ["tracking_code", "store__name", "shop_name", "product__name", "description"]
    ordering_fields = ["created_at", "status"]

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "ثبت شکایت از طریق سایت عمومی انجام می‌شود."})

    def get_serializer_class(self):
        return StoreComplaintSerializer if self.request.user.role == Role.STORE else ComplaintSerializer

    def retrieve(self, request, *args, **kwargs):
        c = self.get_object()
        if request.user.role == Role.CHAMBER and not c.chamber_seen_at:
            c.chamber_seen_at = timezone.now()
            c.save(update_fields=["chamber_seen_at"])
        return Response(self.get_serializer(c).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        c = self.get_object()
        if request.user.role == Role.CHAMBER and c.union_id and request.data.get("status") in services.FINAL:
            # اتاق اصناف فقط شکایات فروشندگان خارج از سامانه یا ارجاعی را می‌بندد
            if not request.data.get("override"):
                raise ValidationError({"status": "رسیدگی با اتحادیه است؛ برای بستن مستقیم override را ارسال کنید."})
        violation = request.data.get("violation_confirmed")
        services.change_status(
            c, request.user, request.data.get("status", c.status), (request.data.get("note") or "").strip(),
            violation=None if violation in (None, "") else bool(violation),
            suspend_store=bool(request.data.get("suspend_store")),
            is_public=request.data.get("is_public", True) not in (False, "false", 0),
        )
        return Response(self.get_serializer(c).data)
