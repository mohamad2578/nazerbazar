from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.views import ScopedModelViewSet
from apps.orgs.models import Store

from . import order_services
from .orders import Order


class OrderItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(source="product_id", read_only=True)
    name = serializers.CharField(read_only=True)
    unit_display = serializers.CharField(read_only=True)
    price = serializers.IntegerField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    line_total = serializers.IntegerField(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_display = serializers.CharField(source="get_delivery_display", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_phone = serializers.CharField(source="store.phone", read_only=True)
    store_address = serializers.CharField(source="store.address", read_only=True)
    events = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "code", "store", "store_name", "store_phone", "store_address", "customer_name", "customer_phone",
            "delivery", "delivery_display", "address", "note", "total", "status", "status_display",
            "store_note", "created_at", "items", "events",
        ]

    def get_events(self, o):
        return [
            {"status_display": e.get_status_display(), "note": e.note, "created_at": e.created_at}
            for e in o.events.all()
        ]


class OrderViewSet(ScopedModelViewSet):
    """کارتابل سفارش‌های فروشگاه (و مشاهده برای سطوح نظارتی)."""

    queryset = Order.objects.select_related("store").prefetch_related("items", "events")
    serializer_class = OrderSerializer
    read_roles = ("governorate", "samt", "chamber", "union", "store")
    write_roles = ("store",)
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "store", "delivery"]
    search_fields = ["code", "customer_name", "customer_phone"]

    def create(self, request, *args, **kwargs):
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"detail": "ثبت سفارش از صفحه فروشگاه در سایت عمومی انجام می‌شود."})

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        order = self.get_object()
        order_services.change_order_status(
            order, request.user, request.data.get("status", ""), (request.data.get("note") or "").strip()
        )
        return Response(self.get_serializer(order).data)

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order(request, pk):
    """ثبت سفارش توسط مشتری از ویترین فروشگاه."""
    store = get_object_or_404(Store, pk=pk)
    order = order_services.place_order(request.user, store, request.data.get("items") or [], request.data)
    return Response(OrderSerializer(order).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    qs = Order.objects.filter(customer=request.user).select_related("store").prefetch_related("items", "events")
    return Response(OrderSerializer(qs[:50], many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_my_order(request, code):
    order = get_object_or_404(Order, code=code.upper(), customer=request.user)
    order_services.change_order_status(order, request.user, Order.Status.CANCELED, "لغو توسط مشتری")
    return Response(OrderSerializer(order).data)
