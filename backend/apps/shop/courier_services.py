"""مدیریت پیک: ارسال لیست سفارش‌ها به پیک و گردش تحویل (تحویل‌گرفتن از فروشگاه ← تحویل به مشتری)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User, notify
from apps.core.utils import normalize_mobile
from apps.orgs.models import Store

from .commerce import Courier
from .orders import Order, OrderEvent

# سفارشی که هنوز دست پیک نیست و می‌شود برایش پیک تعیین یا عوض کرد
ASSIGNABLE = (Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY)


@transaction.atomic
def add_courier(store: Store, mobile: str, first_name: str = "", last_name: str = "") -> Courier:
    mobile = normalize_mobile(mobile)
    if not mobile:
        raise ValidationError({"mobile": "شماره موبایل پیک را وارد کنید."})
    user = User.objects.filter(mobile=mobile).first()
    if user:
        if user.role != Role.CITIZEN or user.stores.exists():
            raise ValidationError({"mobile": "این شماره متعلق به کاربر سازمانی یا فروشگاه است و پیک نمی‌شود."})
        if Courier.objects.filter(user=user).exists():
            raise ValidationError({"mobile": "این شماره قبلا به عنوان پیک ثبت شده است."})
    else:
        user = User.objects.create_user(mobile)
    if first_name or last_name:
        user.first_name, user.last_name = first_name or user.first_name, last_name or user.last_name
        user.save(update_fields=["first_name", "last_name"])
    courier = Courier.objects.create(store=store, user=user)
    notify([user], "شما پیک فروشگاه شدید", f"فروشگاه «{store.name}» شما را به عنوان پیک ثبت کرد.", "/courier")
    return courier


@transaction.atomic
def deactivate_courier(courier: Courier) -> None:
    """پیک غیرفعال می‌شود؛ سفارش‌های ارسال‌شده‌ی هنوز تحویل‌نگرفته از او برداشته می‌شود."""
    if courier.orders.filter(status=Order.Status.OUT_FOR_DELIVERY).exists():
        raise ValidationError({"detail": "این پیک سفارش در مسیر دارد؛ ابتدا تحویل آن‌ها را نهایی کنید."})
    for o in courier.orders.filter(status__in=ASSIGNABLE):
        o.courier, o.assigned_at = None, None
        o.save(update_fields=["courier", "assigned_at", "updated_at"])
        OrderEvent.objects.create(order=o, status=o.status, note="پیک غیرفعال شد؛ سفارش بدون پیک ماند.")
    courier.is_active = False
    courier.save(update_fields=["is_active", "updated_at"])


@transaction.atomic
def assign_orders(store: Store, courier: Courier, order_ids: list[int], by: User) -> list[Order]:
    """ارسال فهرست سفارش‌ها به یک پیک. همه سفارش‌ها باید ارسالی (نه حضوری) و از همین فروشگاه باشند."""
    if courier.store_id != store.pk or not courier.is_active:
        raise ValidationError({"courier": "پیک انتخاب‌شده فعال نیست یا متعلق به این فروشگاه نیست."})
    orders = list(Order.objects.select_for_update().filter(pk__in=order_ids, store=store))
    if not orders or len(orders) != len(set(order_ids)):
        raise ValidationError({"orders": "برخی سفارش‌ها یافت نشد."})
    for o in orders:
        if o.delivery != Order.Delivery.DELIVERY:
            raise ValidationError({"orders": f"سفارش {o.code} حضوری است و پیک نمی‌خواهد."})
        if o.status not in ASSIGNABLE:
            raise ValidationError({"orders": f"سفارش {o.code} در وضعیت «{o.get_status_display()}» است و پیک نمی‌گیرد."})
    now = timezone.now()
    for o in orders:
        o.courier, o.assigned_at = courier, now
        o.save(update_fields=["courier", "assigned_at", "updated_at"])
        OrderEvent.objects.create(order=o, status=o.status, actor=by, note=f"به پیک {courier} سپرده شد.")
    notify(
        [courier.user], f"{len(orders)} سفارش جدید برای تحویل",
        "، ".join(o.code for o in orders[:5]) + ("…" if len(orders) > 5 else ""), "/courier",
    )
    return orders


@transaction.atomic
def unassign_order(order: Order, by: User) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.OUT_FOR_DELIVERY:
        raise ValidationError({"detail": "سفارش دست پیک است؛ از طریق پیک یا «تحویل شد» نهایی شود."})
    if order.courier_id:
        notify([order.courier.user], f"سفارش {order.code} از شما گرفته شد", "", "/courier")
    order.courier, order.assigned_at = None, None
    order.save(update_fields=["courier", "assigned_at", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, actor=by, note="پیک برداشته شد.")
    return order


def _mine(order_id: int, courier: Courier) -> Order:
    order = Order.objects.select_for_update().filter(pk=order_id, courier=courier).first()
    if not order:
        raise ValidationError({"detail": "این سفارش به شما سپرده نشده است."})
    return order


@transaction.atomic
def pickup(order_id: int, courier: Courier) -> Order:
    """پیک بسته را از فروشگاه تحویل گرفت و در مسیر است."""
    order = _mine(order_id, courier)
    if order.status != Order.Status.READY:
        raise ValidationError({"detail": "سفارش هنوز آماده تحویل نیست؛ فروشگاه باید آن را «آماده تحویل» کند."})
    order.status, order.picked_at = Order.Status.OUT_FOR_DELIVERY, timezone.now()
    order.save(update_fields=["status", "picked_at", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, actor=courier.user, note="پیک سفارش را تحویل گرفت.")
    notify([order.customer], f"سفارش {order.code} در مسیر است", f"پیک: {courier} — {courier.user.mobile}", "/orders")
    return order


@transaction.atomic
def deliver(order_id: int, courier: Courier, note: str = "") -> Order:
    """تحویل به مشتری؛ برای پرداخت نقدی، دریافت وجه هم ثبت می‌شود."""
    order = _mine(order_id, courier)
    if order.status != Order.Status.OUT_FOR_DELIVERY:
        raise ValidationError({"detail": "ابتدا باید سفارش را از فروشگاه تحویل بگیرید."})
    now = timezone.now()
    order.status, order.delivered_at, order.closed_at = Order.Status.DELIVERED, now, now
    if order.payment_method == Order.Payment.CASH:
        order.payment_status = Order.PaymentStatus.PAID
    order.save(update_fields=["status", "delivered_at", "closed_at", "payment_status", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, actor=courier.user, note=note or "تحویل مشتری شد.")
    notify([order.customer], f"سفارش {order.code} تحویل شد", "از خرید شما سپاسگزاریم.", "/orders")
    notify([order.store.owner], f"سفارش {order.code} تحویل مشتری شد", f"پیک: {courier}", "/panel/orders")
    return order


@transaction.atomic
def fail(order_id: int, courier: Courier, reason: str) -> Order:
    """تحویل ناموفق (مشتری در دسترس نبود و …): سفارش به فروشگاه برمی‌گردد."""
    order = _mine(order_id, courier)
    if order.status != Order.Status.OUT_FOR_DELIVERY:
        raise ValidationError({"detail": "فقط سفارشِ در مسیر را می‌توان ناموفق ثبت کرد."})
    if not reason.strip():
        raise ValidationError({"reason": "دلیل را بنویسید."})
    order.status, order.courier, order.assigned_at, order.picked_at = Order.Status.READY, None, None, None
    order.save(update_fields=["status", "courier", "assigned_at", "picked_at", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, actor=courier.user, note=f"تحویل ناموفق: {reason.strip()}")
    notify([order.store.owner], f"تحویل سفارش {order.code} ناموفق بود", f"{courier}: {reason.strip()}", "/panel/orders")
    return order
