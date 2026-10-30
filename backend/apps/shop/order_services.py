from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User, notify
from apps.core.utils import normalize_mobile, tracking_code
from apps.orgs.models import Store

from . import wallet
from .commerce import ShopBundle, UserAddress, WalletTx
from .models import ShopProduct
from .orders import Order, OrderEvent, OrderItem

MAX_QTY = 99
# سفارش اینترنتی که پرداختش تکمیل نشود پس از این مدت لغو و موجودی‌اش آزاد می‌شود
UNPAID_TTL = timedelta(minutes=30)


def _clean_qty(v) -> int:
    try:
        return max(1, min(MAX_QTY, int(v or 1)))
    except (TypeError, ValueError):
        return 1


def expire_unpaid_orders(store: Store) -> None:
    cutoff = timezone.now() - UNPAID_TTL
    for o in Order.objects.filter(store=store, status=Order.Status.AWAITING_PAYMENT, created_at__lt=cutoff):
        release_unpaid_order(o, "پرداخت در مهلت مقرر انجام نشد")


@transaction.atomic
def place_order(customer: User, store: Store, rows: list[dict], data: dict, bundles: list[dict] | None = None,
                callback_url: str = "") -> Order:
    """ثبت سفارش از ویترین یک فروشگاه. rows: [{product, quantity}]، bundles: [{bundle, quantity}]"""
    if store.status != Store.Status.ACTIVE:
        raise ValidationError({"store": "این فروشگاه در حال حاضر فعال نیست."})
    bundles = bundles or []
    if not rows and not bundles:
        raise ValidationError({"items": "سبد خرید خالی است."})
    expire_unpaid_orders(store)

    # ── اقلام درخواستی (کالاهای تکی + اجزای بسته‌ها) ──
    singles = {int(r["product"]): _clean_qty(r.get("quantity")) for r in rows if r.get("product")}
    bundle_qty = {int(b["bundle"]): _clean_qty(b.get("quantity")) for b in bundles if b.get("bundle")}
    bundle_objs = {
        b.pk: b for b in ShopBundle.objects.filter(pk__in=bundle_qty, store=store, is_active=True).prefetch_related("items")
    }
    if set(bundle_qty) - set(bundle_objs):
        raise ValidationError({"items": "برخی بسته‌های پیشنهادی دیگر موجود نیستند؛ سبد خرید را به‌روز کنید."})

    need: dict[int, int] = dict(singles)
    for bid, bq in bundle_qty.items():
        for it in bundle_objs[bid].items.all():
            need[it.product_id] = need.get(it.product_id, 0) + it.quantity * bq

    products = ShopProduct.objects.select_for_update().filter(
        pk__in=need, store=store, is_active=True, is_available=True, status=ShopProduct.Status.APPROVED
    )
    found = {p.pk: p for p in products}
    if set(need) - set(found):
        raise ValidationError({"items": "برخی کالاها دیگر موجود نیستند؛ سبد خرید را به‌روز کنید."})

    # ── موجودی و سقف خرید هر کاربر ──
    bought = dict(
        OrderItem.objects.filter(order__customer=customer, product__in=found)
        .exclude(order__status=Order.Status.CANCELED)
        .values_list("product").annotate(n=Sum("quantity"))
    )
    for pid, qty in need.items():
        p = found[pid]
        if p.stock is not None and p.stock < qty:
            raise ValidationError({"items": f"«{p.name}» ناموجود است." if p.stock <= 0 else
                                   f"از «{p.name}» بیش از {p.stock} عدد موجود نیست."})
        if p.per_user_limit is not None:
            left = max(0, p.per_user_limit - (bought.get(pid) or 0))
            if qty > left:
                raise ValidationError({"items": f"سقف خرید «{p.name}» برای هر کاربر {p.per_user_limit} عدد است"
                                                + (f" و شما {left} عدد دیگر می‌توانید بخرید." if left else " و سهمیه شما تکمیل شده است.")})

    # ── تحویل و نشانی ──
    phone = normalize_mobile(data.get("customer_phone") or customer.mobile)
    delivery = data.get("delivery") or Order.Delivery.PICKUP
    address, lat, lng = (data.get("address") or "").strip(), data.get("lat") or None, data.get("lng") or None
    if delivery == Order.Delivery.DELIVERY:
        if data.get("address_id"):
            saved = UserAddress.objects.filter(pk=data["address_id"], user=customer).first()
            if not saved:
                raise ValidationError({"address": "نشانی انتخاب‌شده یافت نشد."})
            address, lat, lng = saved.address, saved.lat, saved.lng
            phone = normalize_mobile(saved.receiver_phone) if saved.receiver_phone else phone
        if not address:
            raise ValidationError({"address": "برای ارسال به نشانی، نشانی را وارد یا انتخاب کنید."})
        if store.is_featured and (lat is None or lng is None or lat == "" or lng == ""):
            raise ValidationError({"address": "موقعیت نشانی روی نقشه را مشخص کنید تا پیک بتواند پیدا کند."})
    else:
        address, lat, lng = "", None, None

    method = data.get("payment_method") or Order.Payment.CASH
    if method not in Order.Payment.values:
        raise ValidationError({"payment_method": "روش پرداخت نامعتبر است."})
    if store.is_featured:
        # فروشگاه ویژه فقط با پرداخت اینترنتی و ارسال با پیک می‌فروشد
        if method != Order.Payment.ONLINE:
            raise ValidationError({"payment_method": "خرید از فروشگاه ویژه فقط با پرداخت اینترنتی انجام می‌شود."})
        if delivery != Order.Delivery.DELIVERY:
            raise ValidationError({"delivery": "سفارش‌های فروشگاه ویژه فقط با پیک ارسال می‌شود."})

    order = Order.objects.create(
        code=tracking_code("S"), store=store, customer=customer,
        customer_name=(data.get("customer_name") or customer.full_name or "مشتری").strip(), customer_phone=phone,
        delivery=delivery, address=address, lat=lat, lng=lng, note=(data.get("note") or "").strip(),
        payment_method=method,
        status=Order.Status.AWAITING_PAYMENT if method == Order.Payment.ONLINE else Order.Status.NEW,
    )

    # ── اقلام سفارش و محاسبه مبلغ ──
    gross, discount = 0, 0
    for pid, qty in singles.items():
        p = found[pid]
        OrderItem.objects.create(order=order, product=p, name=p.name, unit_display=p.get_unit_display(),
                                 price=p.price, list_price=max(p.old_price or 0, p.price), quantity=qty)
        gross += p.price * qty
    for bid, bq in bundle_qty.items():
        b = bundle_objs[bid]
        unit_sum = 0
        for it in b.items.all():
            p = found[it.product_id]
            OrderItem.objects.create(order=order, product=p, name=p.name, unit_display=p.get_unit_display(),
                                     price=p.price, list_price=max(p.old_price or 0, p.price), bundle_name=b.title,
                                     quantity=it.quantity * bq)
            unit_sum += p.price * it.quantity
        gross += unit_sum * bq
        discount += max(0, unit_sum - b.price) * bq
    order.discount = discount
    order.total = gross - discount
    order.save(update_fields=["discount", "total"])

    for pid, qty in need.items():
        p = found[pid]
        if p.stock is not None:
            p.stock -= qty
            p.save(update_fields=["stock", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, actor=customer, note="سفارش ثبت شد.")

    # ── پرداخت ──
    order.payment_url = ""
    if method == Order.Payment.WALLET:
        wallet.debit(customer, order.total, WalletTx.Kind.ORDER, f"پرداخت سفارش {order.code}", order=order)
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])
        _notify_store(order)
    elif method == Order.Payment.ONLINE:
        from . import payments

        sep = "&" if "?" in callback_url else "?"
        _, order.payment_url = payments.start(
            customer, order.total, "order", f"{callback_url}{sep}order={order.code}", order=order,
            description=f"سفارش {order.code} — {store.name}",
        )
    else:
        _notify_store(order)
    return order


def _notify_store(order: Order) -> None:
    notify(
        [order.store.owner], f"سفارش جدید {order.code}",
        f"{order.customer_name} — {order.total:,} ریال ({order.items.count()} قلم)", "/panel/orders",
    )


@transaction.atomic
def mark_order_paid(order: Order) -> None:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.payment_status == Order.PaymentStatus.PAID:
        return
    if order.status == Order.Status.CANCELED:
        # پرداخت بعد از لغو (مثلا پس از انقضای مهلت) به کیف پول برمی‌گردد تا پول مشتری نسوزد
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])
        _refund(order, "پرداخت پس از لغو سفارش")
        return
    order.payment_status = Order.PaymentStatus.PAID
    if order.status == Order.Status.AWAITING_PAYMENT:
        order.status = Order.Status.NEW
    order.save(update_fields=["payment_status", "status", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, note="پرداخت اینترنتی انجام شد.")
    _notify_store(order)


def _restore_stock(order: Order) -> None:
    for it in order.items.select_related("product"):
        p = it.product
        if p and p.stock is not None:
            ShopProduct.objects.filter(pk=p.pk).update(stock=p.stock + it.quantity)
            p.stock += it.quantity


def _refund(order: Order, note: str) -> None:
    if order.payment_status == Order.PaymentStatus.PAID and order.total:
        wallet.credit(order.customer, order.total, WalletTx.Kind.REFUND, f"{note} — سفارش {order.code}", order=order)
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=["payment_status"])


@transaction.atomic
def release_unpaid_order(order: Order, note: str) -> None:
    """لغو سفارش اینترنتیِ پرداخت‌نشده و آزادکردن موجودی."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.AWAITING_PAYMENT:
        return
    order.status = Order.Status.CANCELED
    order.closed_at = timezone.now()
    order.save(update_fields=["status", "closed_at", "updated_at"])
    _restore_stock(order)
    OrderEvent.objects.create(order=order, status=order.status, note=note)


# وضعیت‌هایی که فروشنده از هر وضعیت می‌تواند به آن‌ها برود
STORE_TRANSITIONS = {
    Order.Status.NEW: {Order.Status.CONFIRMED, Order.Status.CANCELED},
    Order.Status.CONFIRMED: {Order.Status.PREPARING, Order.Status.READY, Order.Status.CANCELED},
    Order.Status.PREPARING: {Order.Status.READY, Order.Status.CANCELED},
    Order.Status.READY: {Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED, Order.Status.CANCELED},
    Order.Status.OUT_FOR_DELIVERY: {Order.Status.DELIVERED, Order.Status.READY, Order.Status.CANCELED},
}


@transaction.atomic
def change_order_status(order: Order, actor: User, status: str, note: str = "") -> Order:
    if status not in Order.Status.values:
        raise ValidationError({"status": "وضعیت نامعتبر است."})
    order = Order.objects.select_for_update().get(pk=order.pk)
    is_customer = order.customer_id == actor.pk
    if is_customer:
        # مشتری فقط تا پیش از آماده‌سازی می‌تواند سفارش خود را لغو کند
        if status != Order.Status.CANCELED or order.status not in (
            Order.Status.AWAITING_PAYMENT, Order.Status.NEW, Order.Status.CONFIRMED
        ):
            raise ValidationError({"status": "در این مرحله امکان لغو توسط شما وجود ندارد."})
    elif status not in STORE_TRANSITIONS.get(order.status, set()):
        raise ValidationError({"status": "تغییر وضعیت از این مرحله مجاز نیست."})

    order.status = status
    if note:
        order.store_note = note
    if status in (Order.Status.DELIVERED, Order.Status.CANCELED):
        order.closed_at = timezone.now()
    if status == Order.Status.DELIVERED:
        order.delivered_at = timezone.now()
    if status == Order.Status.DELIVERED and order.payment_method == Order.Payment.CASH:
        order.payment_status = Order.PaymentStatus.PAID    # پول نقد هنگام تحویل دریافت شد
    order.save()
    if status == Order.Status.CANCELED:
        _restore_stock(order)
        _refund(order, "لغو سفارش")
    OrderEvent.objects.create(order=order, status=status, actor=actor, note=note)
    if status == Order.Status.CANCELED and order.courier_id:
        notify([order.courier.user], f"سفارش {order.code} لغو شد", "نیازی به تحویل نیست.", "/courier")

    target = order.customer if not is_customer else order.store.owner
    notify([target], f"سفارش {order.code}: {order.get_status_display()}", note, "/panel/orders" if is_customer else "/orders")
    return order
