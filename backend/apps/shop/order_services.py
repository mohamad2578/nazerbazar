"""منطق ثبت و گردش سفارش (لایه سرویس؛ نه API).

`place_order` در یک تراکنش: اعتبارسنجی اقلام/بسته‌ها، قفل ردیف کالاها، کنترل موجودی و سقف خرید هر کاربر، محاسبه مبلغ (تخفیف بسته،
مالیات و هزینه ارسال فروشگاه ویژه)، شماره فاکتور و کسر موجودی از دفتر انبار. **تماس با درگاه داخل تراکنش نیست**:
بعد از ثبت، `start_online_payment` صدا زده می‌شود و در صورت خطا سفارش لغو و موجودی آزاد می‌شود.

وضعیت‌ها: awaiting_payment → new → confirmed → preparing → ready → out_for_delivery → delivered، و canceled.
لغو: موجودی برمی‌گردد و پرداخت‌شده به کیف پول بازگردانده می‌شود. سفارش اینترنتیِ پرداخت‌نشده بعد از `UNPAID_TTL` (۳۰ دقیقه) با
`expire_unpaid_orders` (از `daily_jobs` و ویترین) لغو می‌شود.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User, notify
from apps.core.utils import normalize_mobile, tracking_code
from apps.orgs.models import Store

from . import inventory, wallet
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


def _qty_map(rows, key: str) -> dict[int, int]:
    """[{product|bundle: id, quantity: n}] را امن به {id: n} تبدیل می‌کند (ورودی نامعتبر → خطای ۴۰۰ نه ۵۰۰)."""
    out: dict[int, int] = {}
    if not isinstance(rows, list):
        raise ValidationError({"items": "فهرست اقلام نامعتبر است."})
    for r in rows[:100]:
        if not isinstance(r, dict) or not r.get(key):
            continue
        try:
            pk = int(r[key])
        except (TypeError, ValueError):
            raise ValidationError({"items": "شناسه کالا نامعتبر است."})
        out[pk] = out.get(pk, 0) + _clean_qty(r.get("quantity"))
    return out


def _coord(v, lo: float, hi: float):
    """مختصات جغرافیایی را اعتبارسنجی و به ۶ رقم اعشار گرد می‌کند؛ مقدار خالی None است."""
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValidationError({"address": "موقعیت نقشه نامعتبر است."})
    if not lo <= f <= hi:
        raise ValidationError({"address": "موقعیت نقشه نامعتبر است."})
    return round(f, 6)


def expire_unpaid_orders(store: Store | None = None, limit: int = 100) -> int:
    """سفارش‌های اینترنتی پرداخت‌نشده‌ی قدیمی‌تر از مهلت را لغو و موجودی‌شان را آزاد می‌کند (دسته‌ای، با سقف)."""
    cutoff = timezone.now() - UNPAID_TTL
    qs = Order.objects.filter(status=Order.Status.AWAITING_PAYMENT, created_at__lt=cutoff)
    if store is not None:
        qs = qs.filter(store=store)
    n = 0
    for o in qs.order_by("created_at")[:limit]:
        release_unpaid_order(o, "پرداخت در مهلت مقرر انجام نشد")
        n += 1
    return n


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
    singles = {pk: min(MAX_QTY, q) for pk, q in _qty_map(rows, "product").items()}
    bundle_qty = {pk: min(MAX_QTY, q) for pk, q in _qty_map(bundles, "bundle").items()}
    if not singles and not bundle_qty:
        raise ValidationError({"items": "سبد خرید خالی است."})
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
    if delivery not in Order.Delivery.values:
        raise ValidationError({"delivery": "نحوه تحویل نامعتبر است."})
    address = str(data.get("address") or "").strip()[:300]
    lat, lng = _coord(data.get("lat"), -90, 90), _coord(data.get("lng"), -180, 180)
    if delivery == Order.Delivery.DELIVERY:
        if data.get("address_id"):
            try:
                saved = UserAddress.objects.filter(pk=int(data["address_id"]), user=customer).first()
            except (TypeError, ValueError):
                saved = None
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
        customer_name=str(data.get("customer_name") or customer.full_name or "مشتری").strip()[:120], customer_phone=phone,
        delivery=delivery, address=address, lat=lat, lng=lng, note=str(data.get("note") or "").strip()[:1000],
        payment_method=method,
        status=Order.Status.AWAITING_PAYMENT if method == Order.Payment.ONLINE else Order.Status.NEW,
    )

    # ── اقلام سفارش و محاسبه مبلغ ──
    gross, discount = 0, 0
    for pid, qty in singles.items():
        p = found[pid]
        OrderItem.objects.create(order=order, product=p, name=p.name, unit_display=p.get_unit_display(),
                                 price=p.price, list_price=max(p.old_price or 0, p.price), cost_price=p.cost_price,
                                 quantity=qty)
        gross += p.price * qty
    for bid, bq in bundle_qty.items():
        b = bundle_objs[bid]
        unit_sum = 0
        for it in b.items.all():
            p = found[it.product_id]
            OrderItem.objects.create(order=order, product=p, name=p.name, unit_display=p.get_unit_display(),
                                     price=p.price, list_price=max(p.old_price or 0, p.price), cost_price=p.cost_price,
                                     bundle_name=b.title, quantity=it.quantity * bq)
            unit_sum += p.price * it.quantity
        gross += unit_sum * bq
        discount += max(0, unit_sum - b.price) * bq
    goods = gross - discount
    tax = fee = 0
    if store.is_featured:
        # مالیات، هزینه ارسال و شماره فاکتور فقط برای فروشگاه ویژه (طبق تنظیمات مالی خودش)
        fin = inventory.get_settings(store)
        tax = round(goods * fin.vat_percent / 100)
        if delivery == Order.Delivery.DELIVERY and fin.delivery_fee and (
            fin.free_delivery_over is None or goods < fin.free_delivery_over
        ):
            fee = fin.delivery_fee
        order.invoice_no = inventory.next_invoice_no(store)
    order.discount, order.tax, order.delivery_fee = discount, tax, fee
    order.total = goods + tax + fee
    order.save(update_fields=["discount", "tax", "delivery_fee", "total", "invoice_no"])

    for pid, qty in need.items():
        p = found[pid]
        if p.stock is not None:
            inventory.record(p.pk, -qty, inventory.Kind.SALE, ref=order.code, note=f"سفارش {order.code}")
    OrderEvent.objects.create(order=order, status=order.status, actor=customer, note="سفارش ثبت شد.")

    # ── پرداخت ──
    order.payment_url = ""
    if method == Order.Payment.WALLET:
        wallet.debit(customer, order.total, WalletTx.Kind.ORDER, f"پرداخت سفارش {order.code}", order=order)
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])
        _notify_store(order)
    elif method != Order.Payment.ONLINE:
        _notify_store(order)
    # پرداخت اینترنتی: درخواست درگاه بعد از ثبت قطعی سفارش و بیرون از تراکنش انجام می‌شود (start_online_payment)
    return order


def start_online_payment(order: Order, callback_url: str) -> str:
    """درخواست پرداخت به درگاه برای سفارش «در انتظار پرداخت»؛ نشانی پرداخت را برمی‌گرداند.

    اگر درگاه در دسترس نباشد، سفارش همین‌جا لغو و موجودی آزاد می‌شود تا چیزی بی‌دلیل معلق نماند.
    """
    from . import payments

    sep = "&" if "?" in callback_url else "?"
    try:
        _, url = payments.start(
            order.customer, order.total, "order", f"{callback_url}{sep}order={order.code}", order=order,
            description=f"سفارش {order.code} — {order.store.name}", store=order.store,
        )
    except ValidationError:
        release_unpaid_order(order, "درگاه پرداخت در دسترس نبود")
        raise
    return url


def _notify_store(order: Order) -> None:
    notify(
        [order.store.owner], f"سفارش جدید {order.code}",
        f"{order.customer_name} — {order.total:,} ریال ({order.items.count()} قلم)", "/panel/orders",
    )


@transaction.atomic
def mark_order_paid(order: Order, paid_amount: int = 0) -> None:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.payment_status in (Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED):
        # پرداخت دوم برای سفارشی که قبلا پرداخت شده؛ پول مشتری نمی‌سوزد و به کیف پولش برمی‌گردد
        if paid_amount:
            wallet.credit(order.customer, paid_amount, WalletTx.Kind.REFUND, f"پرداخت تکراری سفارش {order.code}", order=order)
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
            inventory.record(p.pk, it.quantity, inventory.Kind.SALE_CANCEL, ref=order.code,
                             unit_cost=it.cost_price or None, note=f"لغو سفارش {order.code}")


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
    note = str(note or "").strip()[:300]
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
        if order.courier_id:
            order.courier_fee = order.courier.fee_per_delivery
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
