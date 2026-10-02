from django.contrib.auth import authenticate
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.views import ScopedModelViewSet

from . import services
from .models import Notification, Role, User

# نقش‌هایی که هر مدیر می‌تواند برای زیرمجموعه خود بسازد
CREATABLE_ROLES = {
    Role.ADMIN: set(Role.values),
    Role.GOVERNORATE: {Role.CHAMBER, Role.UNION},
    Role.CHAMBER: {Role.UNION},
}


class MeSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    store = serializers.SerializerMethodField()
    scope_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "mobile", "first_name", "last_name", "national_code", "role", "role_display",
            "province", "chamber", "union", "store", "scope_name",
        ]
        read_only_fields = ["mobile", "role", "province", "chamber", "union"]

    def get_store(self, u):
        s = u.stores.select_related("union").first()
        if not s:
            return None
        return {"id": s.pk, "name": s.name, "status": s.status, "status_display": s.get_status_display(),
                "status_reason": s.status_reason, "union_name": s.union.name}

    def get_scope_name(self, u):
        target = {"governorate": u.province, "chamber": u.chamber, "union": u.union}.get(u.role)
        return str(target) if target else ""


def token_payload(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": MeSerializer(user).data}


class OTPThrottle(SimpleRateThrottle):
    scope = "otp"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPThrottle])
def otp_request(request):
    otp = services.request_otp(request.data.get("mobile", ""))
    return Response({"detail": "کد تایید ارسال شد.", "ttl": 120, **services.otp_debug_payload(otp)})


@api_view(["POST"])
@permission_classes([AllowAny])
def otp_verify(request):
    user = services.verify_otp(request.data.get("mobile", ""), request.data.get("code", ""))
    return Response(token_payload(user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPThrottle])
def password_login(request):
    """ورود با رمز برای کاربران سازمانی که رمز برایشان تعریف شده است."""
    from apps.core.utils import normalize_mobile

    user = authenticate(request, mobile=normalize_mobile(request.data.get("mobile", "")), password=request.data.get("password", ""))
    if not user:
        return Response({"detail": "موبایل یا رمز عبور اشتباه است."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(token_payload(user))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(MeSerializer(request.user).data)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "link", "is_read", "created_at"]


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    filterset_fields = ["is_read"]

    def get_queryset(self):
        return self.request.user.notifications.all()

    def list(self, request, *args, **kwargs):
        resp = super().list(request, *args, **kwargs)
        resp.data["unread"] = self.get_queryset().filter(is_read=False).count()
        return resp

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({"ok": True})


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    scope_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "mobile", "first_name", "last_name", "national_code", "role", "role_display",
            "province", "chamber", "union", "scope_name", "is_active", "password", "last_login",
        ]
        read_only_fields = ["last_login"]

    def get_scope_name(self, u):
        target = {"governorate": u.province, "chamber": u.chamber, "union": u.union}.get(u.role)
        return str(target) if target else ""

    def validate_mobile(self, v):
        from apps.core.utils import normalize_mobile

        return normalize_mobile(v)

    def validate(self, attrs):
        actor = self.context["request"].user
        role = attrs.get("role", getattr(self.instance, "role", Role.CITIZEN))
        if role not in CREATABLE_ROLES.get(actor.role, set()):
            raise serializers.ValidationError({"role": "مجاز به تعریف کاربر با این نقش نیستید."})
        required = {Role.GOVERNORATE: "province", Role.CHAMBER: "chamber", Role.UNION: "union"}.get(role)
        if required and not attrs.get(required, getattr(self.instance, required, None)):
            raise serializers.ValidationError({required: "حوزه این کاربر را مشخص کنید."})
        return attrs

    def create(self, data):
        password = data.pop("password", "")
        return User.objects.create_user(password=password or None, **data)

    def update(self, instance, data):
        password = data.pop("password", "")
        user = super().update(instance, data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class UserViewSet(ScopedModelViewSet):
    queryset = User.objects.select_related("province", "chamber", "union").order_by("-date_joined")
    serializer_class = UserSerializer
    read_roles = write_roles = ("governorate", "chamber")
    filterset_fields = ["role", "is_active", "province", "chamber", "union"]
    search_fields = ["mobile", "first_name", "last_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role != Role.ADMIN:
            qs = qs.exclude(role__in=[Role.ADMIN, Role.CITIZEN, Role.STORE])
        return qs

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
