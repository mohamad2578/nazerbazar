from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role, User, notify
from apps.core.views import ScopedModelViewSet

from .models import Chamber, County, Province, Store, Union


class ProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = ["id", "name", "lat", "lng", "is_active"]


class CountySerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source="province.name", read_only=True)

    class Meta:
        model = County
        fields = ["id", "province", "province_name", "name", "lat", "lng", "population"]


class ChamberSerializer(serializers.ModelSerializer):
    county_name = serializers.CharField(source="county.name", read_only=True)
    unions_count = serializers.IntegerField(source="unions.count", read_only=True)

    class Meta:
        model = Chamber
        fields = ["id", "county", "county_name", "name", "address", "phone", "unions_count"]


class UnionSerializer(serializers.ModelSerializer):
    chamber_name = serializers.CharField(source="chamber.name", read_only=True)
    county = serializers.IntegerField(source="chamber.county_id", read_only=True)
    county_name = serializers.CharField(source="chamber.county.name", read_only=True)

    class Meta:
        model = Union
        fields = [
            "id", "chamber", "chamber_name", "county", "county_name", "name", "guild", "logo",
            "address", "phone", "lat", "lng", "is_active",
        ]


class StoreSerializer(serializers.ModelSerializer):
    union_name = serializers.CharField(source="union.name", read_only=True)
    county_name = serializers.CharField(source="union.chamber.county.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    owner_mobile = serializers.CharField(source="owner.mobile", read_only=True)
    offers_count = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id", "name", "union", "union_name", "county_name", "license_no", "phone", "address", "lat", "lng",
            "working_hours", "photo", "license_image", "status", "status_display", "status_reason",
            "is_verified", "rating_avg", "rating_count", "owner_name", "owner_mobile", "offers_count",
            "created_at", "reviewed_at",
        ]
        read_only_fields = [
            "status", "status_reason", "is_verified", "rating_avg", "rating_count", "created_at", "reviewed_at",
        ]

    def get_offers_count(self, s):
        return s.offers.count()


class StoreRegisterSerializer(StoreSerializer):
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    national_code = serializers.RegexField(r"^\d{10}$", write_only=True, error_messages={"invalid": "کد ملی ۱۰ رقمی است."})

    class Meta(StoreSerializer.Meta):
        fields = StoreSerializer.Meta.fields + ["first_name", "last_name", "national_code"]

    def validate(self, attrs):
        if attrs.get("lat") is None or attrs.get("lng") is None:
            raise ValidationError({"lat": "موقعیت فروشگاه را روی نقشه مشخص کنید."})
        return attrs


class ProvinceViewSet(ScopedModelViewSet):
    queryset = Province.objects.all()
    serializer_class = ProvinceSerializer
    read_roles = ("governorate", "samt")
    search_fields = ["name"]


class CountyViewSet(ScopedModelViewSet):
    queryset = County.objects.select_related("province")
    serializer_class = CountySerializer
    read_roles = ("governorate", "samt", "chamber")
    write_roles = ("governorate", "samt")
    filterset_fields = ["province"]
    search_fields = ["name"]


class ChamberViewSet(ScopedModelViewSet):
    queryset = Chamber.objects.select_related("county")
    serializer_class = ChamberSerializer
    read_roles = ("governorate", "samt", "chamber")
    write_roles = ("governorate", "samt")
    filterset_fields = ["county"]
    search_fields = ["name"]


class UnionViewSet(ScopedModelViewSet):
    queryset = Union.objects.select_related("chamber__county")
    serializer_class = UnionSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    write_roles = ("governorate", "samt", "chamber")
    filterset_fields = ["chamber", "chamber__county", "is_active"]
    search_fields = ["name", "guild"]


class StoreViewSet(ScopedModelViewSet):
    """کارتابل فروشگاه‌ها؛ تایید/رد/تعلیق توسط اتحادیه، اتاق اصناف، استانداری یا مدیر کل."""

    queryset = Store.objects.select_related("union__chamber__county", "owner")
    serializer_class = StoreSerializer
    read_roles = ("governorate", "samt", "chamber", "union")
    # تایید/رد/تعلیق فروشگاه را اتحادیه، اتاق اصناف، استانداری و مدیر کل انجام می‌دهند
    write_roles = ("union", "chamber", "samt", "governorate")
    http_method_names = ["get", "patch", "post", "head", "options"]
    filterset_fields = ["status", "union", "union__chamber", "union__chamber__county", "is_verified"]
    search_fields = ["name", "address", "owner__mobile", "license_no"]
    ordering_fields = ["created_at", "name", "rating_avg"]

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "فروشگاه‌ها از طریق فرم ثبت‌نام ایجاد می‌شوند."})

    def _set(self, request, new_status, need_reason=False):
        store = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        if need_reason and not reason:
            raise ValidationError({"reason": "دلیل را بنویسید."})
        store.set_status(new_status, request.user, reason)
        if new_status == Store.Status.ACTIVE and store.owner.role == Role.CITIZEN:
            store.owner.role = Role.STORE
            store.owner.save(update_fields=["role"])
        notify([store.owner], f"وضعیت فروشگاه: {store.get_status_display()}", reason, "/panel")
        return Response(StoreSerializer(store, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._set(request, Store.Status.ACTIVE)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._set(request, Store.Status.REJECTED, need_reason=True)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        return self._set(request, Store.Status.SUSPENDED, need_reason=True)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        store = self.get_object()
        store.is_verified = bool(request.data.get("value", True))
        store.save(update_fields=["is_verified"])
        return Response(StoreSerializer(store, context={"request": request}).data)


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def my_store(request):
    """ثبت‌نام فروشگاه (POST)، مشاهده و ویرایش مشخصات (GET/PATCH) توسط مالک"""
    user: User = request.user
    store = user.stores.first()
    if request.method == "GET":
        return Response(StoreSerializer(store, context={"request": request}).data if store else None)
    if request.method == "POST":
        if store:
            raise ValidationError({"detail": "شما قبلا فروشگاه ثبت کرده‌اید."})
        if user.role not in (Role.CITIZEN, Role.STORE):
            raise ValidationError({"detail": "کاربران سازمانی نمی‌توانند فروشگاه ثبت کنند."})
        s = StoreRegisterSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            profile = {k: s.validated_data.pop(k) for k in ("first_name", "last_name", "national_code")}
            for k, v in profile.items():
                setattr(user, k, v)
            user.save(update_fields=list(profile))
            store = s.save(owner=user)
        notify(
            User.objects.filter(role=Role.UNION, union=store.union),
            "درخواست فعال‌سازی فروشگاه",
            f"{store.name} — {user.full_name}",
            "/panel/stores?status=pending",
        )
        return Response(StoreSerializer(store, context={"request": request}).data, status=201)
    if not store:
        raise ValidationError({"detail": "فروشگاهی ثبت نشده است."})
    data = request.data.copy()
    # اتحادیه پس از تایید قابل تغییر نیست؛ تغییر نشانی/مختصات مجاز است
    if store.status == Store.Status.ACTIVE:
        data.pop("union", None)
    s = StoreSerializer(store, data=data, partial=True, context={"request": request})
    s.is_valid(raise_exception=True)
    s.save()
    if store.status == Store.Status.REJECTED:
        store.set_status(Store.Status.PENDING, None)  # ارسال مجدد پس از اصلاح
    return Response(StoreSerializer(store, context={"request": request}).data)


class PublicGeoViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        provinces = Province.objects.filter(is_active=True).prefetch_related("counties")
        return Response([
            {"id": p.id, "name": p.name, "counties": [{"id": c.id, "name": c.name, "lat": c.lat, "lng": c.lng} for c in p.counties.all()]}
            for p in provinces
        ])

    @action(detail=False)
    def unions(self, request):
        qs = Union.objects.filter(is_active=True).select_related("chamber__county")
        if county := request.query_params.get("county"):
            qs = qs.filter(chamber__county_id=county)
        return Response(UnionSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False)
    def chambers(self, request):
        qs = Chamber.objects.select_related("county")
        return Response(ChamberSerializer(qs, many=True).data)
