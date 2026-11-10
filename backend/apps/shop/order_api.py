"""API سفارش‌ها (کارتابل فروشگاه و «سفارش‌های من»)، کیف پول، پرداخت (بازگشت از درگاه)، نشانی‌های مشتری و فاکتور.

نکته‌ها: سفارش «در انتظار پرداخت» در کارتابل فروشگاه دیده نمی‌شود. مسئولان نظارتی (اتحادیه/اتاق/صمت/استانداری) نشانی، مختصات و
تلفن مشتری را نمی‌بینند (`OrderSerializer.to_representation`). منطق ثبت و تغییر وضعیت در `order_services.py` است.
"""
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role, User
from apps.core.utils import normalize_mobile
from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store

from . import order_services, payments, wallet
from .commerce import UserAddress, WalletTx
from .orders import Order


class OrderItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(source="product_id", read_only=True)
    name = serializers.CharField(read_only=True)
    unit_display = serializers.CharField(read_only=True)
    price = serializers.IntegerField(read_only=True)
    list_price = serializers.SerializerMethodField()
    bundle_name = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    line_total = serializers.IntegerField(read_only=True)

    def get_list_price(self, it):
        return max(it.list_price, it.price)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_display = serializers.CharField(source="get_delivery_display", read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_phone = serializers.CharField(source="store.phone", read_only=True)
    store_address = serializers.CharField(source="store.address", read_only=True)
    events = serializers.SerializerMethodField()
    list_total = serializers.SerializerMethodField()
    savings = serializers.SerializerMethodField()
    payment_url = serializers.SerializerMethodField()
    courier_name = serializers.SerializerMethodField()
    courier_mobile = serializers.CharField(source="courier.user.mobile", read_only=True, default="")

    class Meta:
        model = Order
        fields = [
            "id", "code", "store", "store_name", "store_phone", "store_address", "customer_name", "customer_phone",
            "delivery", "delivery_display", "address", "lat", "lng", "note", "total", "discount", "tax", "delivery_fee",
            "invoice_no", "list_total",
            "savings", "payment_method", "payment_method_display", "payment_status", "payment_status_display",
            "status", "status_display", "store_note", "created_at", "items", "events", "payment_url",
            "courier", "courier_name", "courier_mobile", "assigned_at", "picked_at", "delivered_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # مسئولان نظارتی (اتحادیه، اتاق اصناف، صمت، استانداری) نشانی دقیق، مختصات و تلفن مشتری را نمی‌بینند
        user = getattr(self.context.get("request"), "user", None)
        if user and user.is_authenticated and user.role in ("governorate", "samt", "chamber", "union"):
            for k in ("address", "lat", "lng"):
                data[k] = "" if k == "address" else None
            phone = data.get("customer_phone") or ""
            data["customer_phone"] = phone[:4] + "***" + phone[-2:] if len(phone) > 6 else ""
            data["courier_mobile"] = ""
        return data

    def get_events(self, o):
        return [
            {"status_display": e.get_status_display(), "note": e.note, "created_at": e.created_at}
            for e in o.events.all()
        ]

    def get_list_total(self, o):
        """جمع قیمت مصرف‌کننده پیش از هر تخفیف."""
        return sum(max(i.list_price, i.price) * i.quantity for i in o.items.all())

    def get_savings(self, o):
        """مجموع تخفیف: اختلاف قیمت مصرف‌کننده با قیمت فروش + تخفیف بسته‌ها."""
        # صرفه‌جویی مشتری از قیمت کالاها است؛ مالیات و هزینه ارسال جزو تخفیف حساب نمی‌شود
        return self.get_list_total(o) - (o.total - o.tax - o.delivery_fee)

    def get_payment_url(self, o):
        return getattr(o, "payment_url", "")

    def get_courier_name(self, o):
        return (o.courier.user.full_name or o.courier.user.mobile) if o.courier_id else ""


class OrderViewSet(ScopedModelViewSet):
    """کارتابل سفارش‌های فروشگاه (و مشاهده برای سطوح نظارتی)."""
    union_section = "orders"

    queryset = Order.objects.select_related("store", "courier__user").prefetch_related("items", "events")
    serializer_class = OrderSerializer
    read_roles = ("governorate", "samt", "chamber", "union", "store")
    write_roles = ("store",)
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "store", "delivery", "payment_status", "payment_method", "courier"]
    search_fields = ["code", "customer_name", "customer_phone", "invoice_no"]

    def get_queryset(self):
        # سفارش پرداخت‌نشده‌ی اینترنتی هنوز سفارش فروشگاه نیست
        return super().get_queryset().exclude(status=Order.Status.AWAITING_PAYMENT)

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "ثبت سفارش از صفحه فروشگاه در سایت عمومی انجام می‌شود."})

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        order = self.get_object()
        order_services.change_order_status(
            order, request.user, request.data.get("status", ""), str(request.data.get("note") or "").strip()
        )
        order.refresh_from_db()
        return Response(self.get_serializer(order).data)

    @action(detail=True)
    def invoice(self, request, pk=None):
        return Response(invoice_payload(self.get_object()))

    @action(detail=False)
    def summary(self, request):
        qs = self.get_queryset()
        agg = qs.aggregate(
            count=Count("pk"),
            new=Count("pk", filter=Q(status=Order.Status.NEW)),
            open=Count("pk", filter=Q(status__in=Order.OPEN_STATUSES)),
            delivered=Count("pk", filter=Q(status=Order.Status.DELIVERED)),
            revenue=Sum("total", filter=Q(status=Order.Status.DELIVERED)),
        )
        agg["revenue"] = agg["revenue"] or 0
        return Response(agg)


def invoice_payload(order: Order) -> dict:
    """داده کامل فاکتور فروش: مشخصات فروشنده، خریدار، اقلام و جمع‌ها (برای چاپ در مرورگر)."""
    from .inventory import get_settings

    st = order.store
    fin = get_settings(st) if st.is_featured else None
    data = OrderSerializer(order).data
    data["seller"] = {
        "name": st.name, "address": st.address, "phone": st.phone, "photo": st.photo.url if st.photo else None,
        "economic_code": fin.economic_code if fin else "", "national_id": fin.national_id if fin else "",
        "postal_code": fin.postal_code if fin else "", "footer": fin.invoice_footer if fin else "",
        "vat_percent": fin.vat_percent if fin else 0,
    }
    data["buyer"] = {"name": order.customer_name, "phone": order.customer_phone, "address": order.address}
    return data


def _callback_url(request) -> str:
    return request.build_absolute_uri("/api/public/payments/callback/")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order(request, pk):
    """ثبت سفارش توسط مشتری از ویترین فروشگاه."""
    store = get_object_or_404(Store, pk=pk)
    order = order_services.place_order(
        request.user, store, request.data.get("items") or [], request.data,
        bundles=request.data.get("bundles") or [], callback_url=_callback_url(request),
    )
    if order.payment_method == Order.Payment.ONLINE:
        order.payment_url = order_services.start_online_payment(order, _callback_url(request))
    return Response(OrderSerializer(order).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    qs = Order.objects.filter(customer=request.user).select_related("store", "courier__user").prefetch_related("items", "events")
    return Response(OrderSerializer(qs[:50], many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_my_order(request, code):
    order = get_object_or_404(Order, code=code.upper(), customer=request.user)
    order_services.change_order_status(order, request.user, Order.Status.CANCELED, "لغو توسط مشتری")
    order.refresh_from_db()
    return Response(OrderSerializer(order).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_order_invoice(request, code):
    order = get_object_or_404(Order, code=code.upper(), customer=request.user)
    return Response(invoice_payload(order))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pay_my_order(request, code):
    """ادامه پرداخت اینترنتی سفارشی که پرداختش کامل نشده است."""
    order = get_object_or_404(Order, code=code.upper(), customer=request.user)
    if order.status != Order.Status.AWAITING_PAYMENT:
        raise ValidationError({"detail": "این سفارش در انتظار پرداخت نیست."})
    _, url = payments.start(request.user, order.total, "order", f"{_callback_url(request)}?order={order.code}",
                            order=order, description=f"سفارش {order.code}", store=order.store)
    order.payment_url = url
    return Response(OrderSerializer(order).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def payment_callback(request):
    """بازگشت کاربر از درگاه؛ پرداخت را تایید می‌کند و کاربر را به برنامه برمی‌گرداند."""
    q = request.query_params
    # زرین‌پال: Authority و Status=OK ؛ زیبال: trackId و success=1
    authority = q.get("Authority") or q.get("trackId") or ""
    ok = q.get("Status", "").upper() == "OK" or q.get("success") == "1"
    payment = payments.verify(authority, ok) if authority else None
    paid = bool(payment and payment.status == "paid")
    if payment and payment.purpose == "wallet":
        return HttpResponseRedirect(f"/account?wallet={'ok' if paid else 'fail'}")
    code = payment.order.code if payment and payment.order_id else request.query_params.get("order", "")
    return HttpResponseRedirect(f"/orders?pay={'ok' if paid else 'fail'}&code={code}")


# ───────────────────────── کیف پول ─────────────────────────


def _tx(t):
    return {"id": t.pk, "amount": t.amount, "balance_after": t.balance_after, "kind": t.kind,
            "kind_display": t.get_kind_display(), "note": t.note, "created_at": t.created_at}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_wallet(request):
    w = wallet.get_wallet(request.user)
    return Response({"balance": w.balance, "txs": [_tx(t) for t in w.txs.all()[:50]]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_topup(request):
    """شارژ کیف پول از درگاه اینترنتی؛ amount به تومان."""
    try:
        amount = int(request.data.get("amount")) * 10
    except (TypeError, ValueError):
        raise ValidationError({"amount": "مبلغ را به تومان وارد کنید."})
    if not 10_000 <= amount <= 500_000_000:
        raise ValidationError({"amount": "مبلغ شارژ باید بین ۱٬۰۰۰ تا ۵۰٬۰۰۰٬۰۰۰ تومان باشد."})
    _, url = payments.start(request.user, amount, "wallet", _callback_url(request), description="شارژ کیف پول ناظر ۷۲۴")
    return Response({"payment_url": url})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_admin_credit(request):
    """افزایش (یا با مبلغ منفی کاهش) اعتبار کیف پول یک کاربر توسط مدیر کل؛ amount به تومان."""
    if request.user.role != Role.ADMIN:
        raise PermissionDenied("این عملیات فقط برای مدیر کل سامانه مجاز است.")
    user = User.objects.filter(mobile=normalize_mobile(request.data.get("mobile", ""))).first()
    if not user:
        raise ValidationError({"mobile": "کاربری با این شماره پیدا نشد."})
    try:
        amount = int(request.data.get("amount")) * 10
    except (TypeError, ValueError):
        raise ValidationError({"amount": "مبلغ را به تومان وارد کنید."})
    if abs(amount) > 10**13:
        raise ValidationError({"amount": "مبلغ بیش از حد مجاز است."})
    note = (request.data.get("note") or "اعتبار از طرف مدیر").strip()
    if amount > 0:
        w = wallet.credit(user, amount, WalletTx.Kind.ADMIN, note)
    elif amount < 0:
        w = wallet.debit(user, -amount, WalletTx.Kind.ADMIN, note)
    else:
        raise ValidationError({"amount": "مبلغ نمی‌تواند صفر باشد."})
    return Response({"mobile": user.mobile, "balance": w.balance})


# ───────────────────────── نشانی‌های مشتری ─────────────────────────


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = ["id", "title", "address", "receiver_phone", "lat", "lng", "is_default"]

    def validate_receiver_phone(self, v):
        if not v:
            return ""
        try:
            return normalize_mobile(v)
        except Exception:  # noqa: BLE001
            raise serializers.ValidationError("شماره تلفن تحویل‌گیرنده باید موبایل معتبر باشد.")

    def validate_lat(self, v):
        if v is not None and not -90 <= v <= 90:
            raise serializers.ValidationError("عرض جغرافیایی نامعتبر است.")
        return v

    def validate_lng(self, v):
        if v is not None and not -180 <= v <= 180:
            raise serializers.ValidationError("طول جغرافیایی نامعتبر است.")
        return v


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def my_addresses(request):
    qs = UserAddress.objects.filter(user=request.user)
    if request.method == "GET":
        return Response(AddressSerializer(qs, many=True).data)
    if qs.count() >= 10:
        raise ValidationError({"detail": "حداکثر ۱۰ نشانی می‌توانید ذخیره کنید."})
    s = AddressSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    obj = s.save(user=request.user, is_default=s.validated_data.get("is_default") or not qs.exists())
    if obj.is_default:
        qs.exclude(pk=obj.pk).update(is_default=False)
    return Response(AddressSerializer(obj).data, status=201)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def my_address_detail(request, pk):
    obj = get_object_or_404(UserAddress, pk=pk, user=request.user)
    if request.method == "DELETE":
        was_default = obj.is_default
        obj.delete()
        if was_default:
            nxt = UserAddress.objects.filter(user=request.user).first()
            if nxt:
                UserAddress.objects.filter(pk=nxt.pk).update(is_default=True)
        return Response(status=204)
    s = AddressSerializer(obj, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    obj = s.save()
    if obj.is_default:
        UserAddress.objects.filter(user=request.user).exclude(pk=obj.pk).update(is_default=False)
    return Response(AddressSerializer(obj).data)
