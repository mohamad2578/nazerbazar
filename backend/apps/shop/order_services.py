from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, notify
from apps.core.utils import normalize_mobile, tracking_code
from apps.orgs.models import Store

from .models import ShopProduct
from .orders import Order, OrderEvent, OrderItem

MAX_QTY = 99


@transaction.atomic
def place_order(customer: User, store: Store, rows: list[dict], data: dict) -> Order:
    """ثبت سفارش از ویترین یک فروشگاه. rows: [{product, quantity}]"""
    if store.status != Store.Status.ACTIVE:
        raise ValidationError({"store": "این فروشگاه در حال حاضر فعال نیست."})
    if not rows:
        raise ValidationError({"items": "سبد خرید خالی است."})

    wanted = {int(r["product"]): int(r.get("quantity") or 1) for r in rows if r.get("product")}
    products = ShopProduct.objects.select_for_update().filter(
        pk__in=wanted, store=store, is_active=True, is_available=True
    )
    found = {p.pk: p for p in products}
    missing = [pid for pid in wanted if pid not in found]
    if missing:
        raise ValidationError({"items": "برخی کالاها دیگر موجود نیستند؛ سبد خرید را به‌روز کنید."})

    phone = normalize_mobile(data.get("customer_phone") or customer.mobile)
    delivery = data.get("delivery") or Order.Delivery.PICKUP
    address = (data.get("address") or "").strip()
    if delivery == Order.Delivery.DELIVERY and not address:
        raise ValidationError({"address": "برای ارسال به نشانی، نشانی را وارد کنید."})

    order = Order.objects.create(
        code=tracking_code("S"),
        store=store,
        customer=customer,
        customer_name=(data.get("customer_name") or customer.full_name or "مشتری").strip(),
        customer_phone=phone,
        delivery=delivery,
        address=address,
        note=(data.get("note") or "").strip(),
    )
    total = 0
    for pid, qty in wanted.items():
        qty = max(1, min(MAX_QTY, qty))
        p = found[pid]
        OrderItem.objects.create(
            order=order, product=p, name=p.name, unit_display=p.get_unit_display(), price=p.price, quantity=qty
        )
        total += p.price * qty
    order.total = total
    order.save(update_fields=["total"])
    OrderEvent.objects.create(order=order, status=order.status, actor=customer, note="سفارش ثبت شد.")
    notify(
        [store.owner],
        f"سفارش جدید {order.code}",
        f"{order.customer_name} — {total:,} ریال ({len(wanted)} قلم)",
        "/panel/orders",
    )
    return order


# وضعیت‌هایی که فروشنده از هر وضعیت می‌تواند به آن‌ها برود
STORE_TRANSITIONS = {
    Order.Status.NEW: {Order.Status.CONFIRMED, Order.Status.CANCELED},
    Order.Status.CONFIRMED: {Order.Status.PREPARING, Order.Status.READY, Order.Status.CANCELED},
    Order.Status.PREPARING: {Order.Status.READY, Order.Status.CANCELED},
    Order.Status.READY: {Order.Status.DELIVERED, Order.Status.CANCELED},
}


@transaction.atomic
def change_order_status(order: Order, actor: User, status: str, note: str = "") -> Order:
    if status not in Order.Status.values:
        raise ValidationError({"status": "وضعیت نامعتبر است."})
    is_customer = order.customer_id == actor.pk
    if is_customer:
        # مشتری فقط تا پیش از آماده‌سازی می‌تواند سفارش خود را لغو کند
        if status != Order.Status.CANCELED or order.status not in (Order.Status.NEW, Order.Status.CONFIRMED):
            raise ValidationError({"status": "در این مرحله امکان لغو توسط شما وجود ندارد."})
    elif status not in STORE_TRANSITIONS.get(order.status, set()):
        raise ValidationError({"status": "تغییر وضعیت از این مرحله مجاز نیست."})

    order.status = status
    if note:
        order.store_note = note
    if status in (Order.Status.DELIVERED, Order.Status.CANCELED):
        order.closed_at = timezone.now()
    order.save()
    OrderEvent.objects.create(order=order, status=status, actor=actor, note=note)

    target = order.customer if not is_customer else order.store.owner
    notify([target], f"سفارش {order.code}: {order.get_status_display()}", note, "/panel/orders" if is_customer else "/orders")
    return order
