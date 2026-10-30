from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.views import ScopedModelViewSet

from . import courier_services
from .commerce import Courier
from .orders import Order


class CourierSerializer(serializers.ModelSerializer):
    """پیک‌های فروشگاه (مدیریت توسط مدیر فروشگاه)."""

    name = serializers.CharField(source="user.full_name", read_only=True)
    mobile = serializers.CharField(source="user.mobile", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    to_deliver = serializers.IntegerField(read_only=True, default=0)
    on_road = serializers.IntegerField(read_only=True, default=0)
    delivered_today = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Courier
        fields = ["id", "name", "mobile", "store", "store_name", "is_active", "to_deliver", "on_road", "delivered_today"]
        read_only_fields = ["store"]


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
            self._store(), d.get("mobile", ""), (d.get("first_name") or "").strip(), (d.get("last_name") or "").strip()
        )
        return Response(CourierSerializer(self.get_queryset().get(pk=courier.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        courier = self.get_object()
        if request.data.get("is_active") is False or str(request.data.get("is_active")).lower() == "false":
            courier_services.deactivate_courier(courier)
        elif request.data.get("is_active") in (True, "true", "True"):
            courier.is_active = True
            courier.save(update_fields=["is_active", "updated_at"])
        u = courier.user
        for f in ("first_name", "last_name"):
            if f in request.data:
                setattr(u, f, (request.data.get(f) or "").strip())
        u.save(update_fields=["first_name", "last_name"])
        return Response(CourierSerializer(self.get_queryset().get(pk=courier.pk)).data)

    def destroy(self, request, *args, **kwargs):
        courier_services.deactivate_courier(self.get_object())
        return Response(status=204)


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
    return Response({"id": c.pk, "name": c.user.full_name or c.user.mobile, "store": c.store.name})


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
    return _act(request, pk, courier_services.deliver, (request.data.get("note") or "").strip())


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
    ids = [int(i) for i in (request.data.get("orders") or [])]
    if not ids:
        raise ValidationError({"orders": "سفارشی انتخاب نشده است."})
    cid = request.data.get("courier")
    if cid in (None, "", 0):
        for o in Order.objects.filter(pk__in=ids, store=store):
            courier_services.unassign_order(o, request.user)
        return Response({"assigned": 0})
    courier = get_object_or_404(Courier, pk=cid, store=store)
    orders = courier_services.assign_orders(store, courier, ids, request.user)
    return Response({"assigned": len(orders)})
