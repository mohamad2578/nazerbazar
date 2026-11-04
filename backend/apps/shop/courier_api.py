from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.views import ScopedModelViewSet

from . import courier_services, erp_reports
from .commerce import Courier
from .erp import CourierSettlement
from .orders import Order


class CourierSerializer(serializers.ModelSerializer):
    """پیک‌های فروشگاه (مدیریت توسط مدیر فروشگاه)."""

    name = serializers.CharField(source="user.full_name", read_only=True)
    mobile = serializers.CharField(source="user.mobile", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    to_deliver = serializers.IntegerField(read_only=True, default=0)
    on_road = serializers.IntegerField(read_only=True, default=0)
    delivered_today = serializers.IntegerField(read_only=True, default=0)

    cash_on_hand = serializers.SerializerMethodField()
    fee_due = serializers.SerializerMethodField()

    class Meta:
        model = Courier
        fields = ["id", "name", "mobile", "store", "store_name", "is_active", "is_online", "fee_per_delivery", "to_deliver",
                  "on_road", "delivered_today", "cash_on_hand", "fee_due"]
        read_only_fields = ["store"]

    def _ledger(self, c):
        cache = self.context.setdefault("_ledger", {})
        if c.pk not in cache:
            cache[c.pk] = erp_reports.courier_ledger(c)
        return cache[c.pk]

    def get_cash_on_hand(self, c):
        return self._ledger(c)["cash_on_hand"]

    def get_fee_due(self, c):
        return self._ledger(c)["fee_due"]


class CourierViewSet(ScopedModelViewSet):
    """مدیر فروشگاه پیک‌هایش را تعریف می‌کند و لیست سفارش‌ها را به آن‌ها می‌سپارد."""

    queryset = Courier.objects.select_related("user", "store")
    serializer_class = CourierSerializer
    read_roles = ("store",)
    write_roles = ("store",)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        today = timezone.localdate()
        return super().get_queryset().annotate(
            to_deliver=Count("orders", filter=Q(orders__status__in=courier_services.ASSIGNABLE), distinct=True),
            on_road=Count("orders", filter=Q(orders__status=Order.Status.OUT_FOR_DELIVERY), distinct=True),
            delivered_today=Count(
                "orders", filter=Q(orders__status=Order.Status.DELIVERED, orders__delivered_at__date=today), distinct=True
            ),
        )

    def _store(self):
        store = self.request.user.stores.first()
        if not store or store.status != "active":
            raise ValidationError({"detail": "فروشگاه فعالی برای شما ثبت نشده است."})
        return store

    def create(self, request, *args, **kwargs):
        d = request.data
        courier = courier_services.add_courier(
            self._store(), str(d.get("mobile", "")), str(d.get("first_name") or "").strip(), str(d.get("last_name") or "").strip()
        )
        return Response(CourierSerializer(self.get_queryset().get(pk=courier.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        courier = self.get_object()
        if request.data.get("is_active") is False or str(request.data.get("is_active")).lower() == "false":
            courier_services.deactivate_courier(courier)
        elif request.data.get("is_active") in (True, "true", "True"):
            courier.is_active = True
            courier.save(update_fields=["is_active", "updated_at"])
        if "fee_per_delivery" in request.data:
            try:
                courier.fee_per_delivery = min(10**10, max(0, int(request.data["fee_per_delivery"])))
            except (TypeError, ValueError):
                raise ValidationError({"fee_per_delivery": "کارمزد را به ریال و عدد وارد کنید."})
            courier.save(update_fields=["fee_per_delivery", "updated_at"])
        if "is_online" in request.data:
            courier.is_online = request.data["is_online"] in (True, "true", "True", 1, "1")
            courier.save(update_fields=["is_online", "updated_at"])
        u = courier.user
        for f in ("first_name", "last_name"):
            if f in request.data:
                setattr(u, f, str(request.data.get(f) or "").strip()[:80])
        u.save(update_fields=["first_name", "last_name"])
        return Response(CourierSerializer(self.get_queryset().get(pk=courier.pk)).data)

    def destroy(self, request, *args, **kwargs):
        courier_services.deactivate_courier(self.get_object())
        return Response(status=204)

    @action(detail=True)
    def ledger(self, request, pk=None):
        """حساب پیک: وجه نقد دردست، کارمزد پرداخت‌نشده، تسویه‌ها و تحویل‌های اخیر."""
        c = self.get_object()
        recent = Order.objects.filter(courier=c, status=Order.Status.DELIVERED).order_by("-delivered_at")[:30]
        return Response({
            **erp_reports.courier_ledger(c),
            "settlements": [{"id": s.pk, "kind": s.kind, "kind_display": s.get_kind_display(), "amount": s.amount, "note": s.note,
                             "created_at": s.created_at} for s in c.settlements.all()[:50]],
            "recent": [{"code": o.code, "customer": o.customer_name, "total": o.total, "payment": o.get_payment_method_display(),
                            "fee": o.courier_fee, "delivered_at": o.delivered_at} for o in recent],
        })

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def settle(self, request, pk=None):
        """ثبت تسویه با پیک: {kind: cash|fee, amount (ریال), note}"""
        c = Courier.objects.select_for_update().get(pk=self.get_object().pk)     # قفل: دو تسویه هم‌زمان از مانده بیشتر نشود
        kind = request.data.get("kind")
        if kind not in CourierSettlement.Kind.values:
            raise ValidationError({"kind": "نوع تسویه نامعتبر است."})
        try:
            amount = int(request.data.get("amount"))
        except (TypeError, ValueError):
            raise ValidationError({"amount": "مبلغ را به ریال وارد کنید."})
        led = erp_reports.courier_ledger(c)
        if amount <= 0:
            raise ValidationError({"amount": "مبلغ باید بیشتر از صفر باشد."})
        if kind == CourierSettlement.Kind.CASH_HANDOVER and amount > led["cash_on_hand"]:
            raise ValidationError({"amount": f"مبلغ از وجه نقد دردست پیک ({led['cash_on_hand']:,} ریال) بیشتر است."})
        if kind == CourierSettlement.Kind.FEE_PAYOUT and amount > led["fee_due"]:
            raise ValidationError({"amount": f"مبلغ از کارمزد پرداخت‌نشده ({led['fee_due']:,} ریال) بیشتر است."})
        CourierSettlement.objects.create(courier=c, kind=kind, amount=amount, note=(request.data.get("note") or "")[:200],
                                         created_by=request.user)
        return Response(erp_reports.courier_ledger(c), status=201)


# ───────────────────────── اپلیکیشن پیک ─────────────────────────


def _courier(request) -> Courier:
    c = Courier.objects.select_related("store", "user").filter(user=request.user, is_active=True).first()
    if not c:
        raise PermissionDenied("شما پیک فعال هیچ فروشگاهی نیستید.")
    return c


class CourierOrderSerializer(serializers.ModelSerializer):
    """اطلاعاتی که پیک برای تحویل لازم دارد (بدون جزئیات مالی غیرضروری)."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_phone = serializers.CharField(source="store.phone", read_only=True)
    store_address = serializers.CharField(source="store.address", read_only=True)
    store_lat = serializers.DecimalField(source="store.lat", max_digits=9, decimal_places=6, read_only=True)
    store_lng = serializers.DecimalField(source="store.lng", max_digits=9, decimal_places=6, read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    cash_due = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "code", "status", "status_display", "store_name", "store_phone", "store_address", "store_lat",
            "store_lng", "customer_name", "customer_phone", "address", "lat", "lng", "note", "store_note", "total",
            "payment_method", "payment_method_display", "payment_status", "cash_due", "items", "assigned_at",
            "picked_at", "delivered_at",
        ]

    def get_cash_due(self, o):
        """مبلغی که پیک باید هنگام تحویل از مشتری بگیرد."""
        unpaid_cash = o.payment_method == Order.Payment.CASH and o.payment_status != Order.PaymentStatus.PAID
        return o.total if unpaid_cash else 0

    def get_items(self, o):
        return [{"name": i.name, "quantity": i.quantity, "unit_display": i.unit_display} for i in o.items.all()]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def courier_me(request):
    c = _courier(request)
    return Response({"id": c.pk, "name": c.user.full_name or c.user.mobile, "store": c.store.name, "is_online": c.is_online,
                     "fee_per_delivery": c.fee_per_delivery})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def courier_stats(request):
    """آمار شخصی پیک: تحویل امروز/هفته/ماه، درآمد کارمزد، وجه نقد دردست و کارمزد دریافت‌نشده."""
    from datetime import timedelta

    c = _courier(request)
    today = timezone.localdate()
    done = Order.objects.filter(courier=c, status=Order.Status.DELIVERED)

    def count(days):
        return done.filter(delivered_at__date__gte=today - timedelta(days=days - 1)).count()

    led = erp_reports.courier_ledger(c)
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        days.append({"date": d.isoformat(), "deliveries": done.filter(delivered_at__date=d).count()})
    return Response({
        "today": count(1), "week": count(7), "month": count(30), "total": led["deliveries"],
        "fee_today": sum(o.courier_fee for o in done.filter(delivered_at__date=today)),
        "cash_on_hand": led["cash_on_hand"], "fee_due": led["fee_due"], "fee_earned": led["fee_earned"], "days": days,
        "active": Order.objects.filter(courier=c, status__in=(*courier_services.ASSIGNABLE, Order.Status.OUT_FOR_DELIVERY)).count(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def courier_online(request):
    """پیک خودش را آنلاین/آفلاین می‌کند؛ مدیر فروشگاه فقط به پیک آنلاین پیشنهاد سفارش می‌دهد."""
    c = _courier(request)
    c.is_online = request.data.get("online") in (True, "true", "True", 1, "1")
    c.save(update_fields=["is_online", "updated_at"])
    return Response({"is_online": c.is_online})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def courier_orders(request):
    """سفارش‌های پیک. scope=active (پیش‌فرض: در انتظار تحویل/در مسیر) یا done (تحویل‌شده‌های اخیر)."""
    c = _courier(request)
    qs = Order.objects.filter(courier=c).select_related("store").prefetch_related("items")
    if request.query_params.get("scope") == "done":
        qs = Order.objects.filter(courier=c, status=Order.Status.DELIVERED).select_related("store").prefetch_related("items")
        qs = qs.order_by("-delivered_at")[:40]
    else:
        qs = qs.filter(status__in=(*courier_services.ASSIGNABLE, Order.Status.OUT_FOR_DELIVERY)).order_by("assigned_at")
    return Response(CourierOrderSerializer(qs, many=True).data)


def _act(request, pk, fn, *args):
    c = _courier(request)
    order = fn(pk, c, *args)
    order = Order.objects.select_related("store").prefetch_related("items").get(pk=order.pk)
    return Response(CourierOrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def courier_pickup(request, pk):
    return _act(request, pk, courier_services.pickup)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def courier_deliver(request, pk):
    return _act(request, pk, courier_services.deliver, str(request.data.get("note") or "").strip())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def courier_fail(request, pk):
    return _act(request, pk, courier_services.fail, request.data.get("reason") or "")


# ───────────────────────── ارسال لیست سفارش‌ها (مدیر فروشگاه) ─────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_orders(request):
    """{courier: <id>, orders: [<id>, …]} — سفارش‌های ارسالی را به یک پیک می‌سپارد؛ courier=null پیک را برمی‌دارد."""
    store = request.user.stores.first()
    if request.user.role != "store" or not store:
        raise PermissionDenied("فقط مدیر فروشگاه می‌تواند سفارش را به پیک بسپارد.")
    raw = request.data.get("orders") or []
    try:
        ids = [int(i) for i in raw][:200] if isinstance(raw, list) else []
    except (TypeError, ValueError):
        raise ValidationError({"orders": "شناسه سفارش‌ها نامعتبر است."})
    if not ids:
        raise ValidationError({"orders": "سفارشی انتخاب نشده است."})
    cid = request.data.get("courier")
    if cid in (None, "", 0):
        for o in Order.objects.filter(pk__in=ids, store=store):
            courier_services.unassign_order(o, request.user)
        return Response({"assigned": 0})
    try:
        courier = get_object_or_404(Courier, pk=int(cid), store=store)
    except (TypeError, ValueError):
        raise ValidationError({"courier": "پیک نامعتبر است."})
    orders = courier_services.assign_orders(store, courier, ids, request.user)
    return Response({"assigned": len(orders)})
