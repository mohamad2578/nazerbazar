from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.api import OTPThrottle
from apps.core.permissions import role_permission
from apps.core.utils import normalize_mobile

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "first_name", "last_name", "mobile", "product_type", "is_reviewed", "created_at"]


class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    """فهرست تامین‌کنندگان برای اداره صمت، استانداری و مدیر کل."""

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    pagination_class = None

    def get_permissions(self):
        return [role_permission("samt", "governorate")()]


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPThrottle])
def public_supplier_register(request):
    """فرم عمومی ثبت‌نام تامین‌کننده؛ نیازی به ورود ندارد."""
    data = request.data
    mobile = normalize_mobile(data.get("mobile", ""))
    errors = {}
    if not (data.get("first_name") or "").strip():
        errors["first_name"] = "نام را وارد کنید."
    if not (data.get("last_name") or "").strip():
        errors["last_name"] = "نام خانوادگی را وارد کنید."
    if not mobile:
        errors["mobile"] = "شماره تماس معتبر وارد کنید."
    if not (data.get("product_type") or "").strip():
        errors["product_type"] = "نوع کالایی که می‌توانید تامین کنید را بنویسید."
    if errors:
        return Response(errors, status=400)
    # اگر همان شماره قبلا فرم را پر کرده، اطلاعاتش به‌روز می‌شود و تکراری ساخته نمی‌شود
    Supplier.objects.update_or_create(
        mobile=mobile,
        defaults={
            "first_name": data["first_name"].strip(),
            "last_name": data["last_name"].strip(),
            "product_type": data["product_type"].strip(),
            "is_reviewed": False,
        },
    )
    return Response({"ok": True}, status=201)
