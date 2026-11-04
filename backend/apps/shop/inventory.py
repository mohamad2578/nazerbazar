"""منطق انبارداری فروشگاه ویژه: ثبت حرکت کالا، فاکتور خرید با میانگین موزون، تعدیل موجودی و تنظیمات مالی.

همه تغییرهای موجودی فقط از `record()` می‌گذرد تا دفتر حرکت کالا همیشه با موجودی واقعی یکی باشد.
کالایی که موجودی (stock) آن خالی است «نامحدود» حساب می‌شود و در دفتر انبار حرکتی ندارد.
"""
from datetime import date as date_cls
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .erp import PurchaseInvoice, PurchaseItem, StockMovement, StoreSettings, Supplier, SupplierPayment
from .models import ShopProduct

Kind = StockMovement.Kind


def get_settings(store) -> StoreSettings:
    s, _ = StoreSettings.objects.get_or_create(store=store)
    return s


def _round(x: Decimal | float) -> int:
    return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@transaction.atomic
def record(product_id: int, delta: int, kind: str, *, ref: str = "", note: str = "", by=None,
           unit_cost: int | None = None, allow_negative: bool = False) -> StockMovement | None:
    """یک حرکت در انبار ثبت می‌کند و موجودی (و در خرید، قیمت تمام‌شده) را به‌روز می‌کند.

    delta مثبت = ورود و منفی = خروج. برای کالای «نامحدود» در فروش/بازگشت، چیزی ثبت نمی‌شود.
    """
    p = ShopProduct.objects.select_for_update().get(pk=product_id)
    if p.stock is None and kind in (Kind.SALE, Kind.SALE_CANCEL):
        return None
    cur = p.stock or 0
    new = cur + delta
    if new > 2_000_000_000:
        raise ValidationError({"qty": "موجودی از حد مجاز سامانه بیشتر می‌شود."})
    if new < 0 and not allow_negative:
        raise ValidationError({"qty": f"موجودی «{p.name}» کافی نیست (موجودی فعلی {cur})."})

    if kind == Kind.PURCHASE and unit_cost is not None and delta > 0:
        # میانگین موزون: موجودی قبلی با قیمت تمام‌شده قبلی + ورودی جدید
        p.cost_price = unit_cost if cur <= 0 else _round(Decimal(cur * p.cost_price + delta * unit_cost) / (cur + delta))
    move_cost = unit_cost if unit_cost is not None else p.cost_price
    p.stock = new
    p.save(update_fields=["stock", "cost_price", "updated_at"])
    mv = StockMovement.objects.create(
        store_id=p.store_id, product=p, kind=kind, qty=delta, unit_cost=move_cost, balance_after=new,
        ref=ref[:40], note=note[:200], by=by,
    )
    if delta < 0 and p.min_stock and cur > p.min_stock >= new:
        # عبور از حد سفارش مجدد؛ فقط یک‌بار (هنگام عبور) به مالک فروشگاه اعلان می‌رود
        from apps.accounts.models import notify

        notify([p.store.owner], f"کمبود موجودی: {p.name}",
               f"موجودی به {new} رسید (حد سفارش مجدد {p.min_stock}). خرید جدید ثبت کنید.", "/panel/erp/inventory")
    return mv


@transaction.atomic
def adjust(product: ShopProduct, *, set_to: int | None = None, delta: int | None = None, kind: str = Kind.ADJUST,
           note: str = "", by=None) -> StockMovement | None:
    """تعدیل دستی: شمارش جدید (انبارگردانی) یا افزایش/کاهش مشخص؛ ضایعات و برگشت به تامین‌کننده همیشه کاهشی است."""
    if kind not in (Kind.ADJUST, Kind.DAMAGE, Kind.SUPPLIER_RETURN, Kind.OPENING):
        raise ValidationError({"kind": "نوع حرکت نامعتبر است."})
    cur = ShopProduct.objects.select_for_update().get(pk=product.pk).stock or 0
    if set_to is not None:
        if set_to < 0:
            raise ValidationError({"value": "موجودی نمی‌تواند منفی باشد."})
        d = set_to - cur
    elif delta is not None:
        d = delta
    else:
        raise ValidationError({"value": "مقدار را وارد کنید."})
    if kind in (Kind.DAMAGE, Kind.SUPPLIER_RETURN):
        d = -abs(d)
    if d == 0:
        raise ValidationError({"value": "تغییری در موجودی ایجاد نمی‌شود."})
    return record(product.pk, d, kind, note=note, by=by)


def next_invoice_no(store) -> str:
    """شماره فاکتور ترتیبی فروشگاه (مثل F000123)؛ باید داخل تراکنش و با قفل ردیف تنظیمات صدا زده شود."""
    s = StoreSettings.objects.select_for_update().get_or_create(store=store)[0]
    s.invoice_seq += 1
    s.save(update_fields=["invoice_seq", "updated_at"])
    return f"{s.invoice_prefix or 'F'}{s.invoice_seq:06d}"


@transaction.atomic
def create_purchase(store, supplier: Supplier, items: list[dict], *, date: date_cls, number: str = "", note: str = "",
                    discount: int = 0, tax: int = 0, shipping: int = 0, paid: int = 0, by=None) -> PurchaseInvoice:
    """ثبت فاکتور خرید: موجودی هر کالا زیاد و قیمت تمام‌شده با هزینه حمل و تخفیف تسهیم‌شده به‌روز می‌شود."""
    if supplier.store_id != store.pk:
        raise ValidationError({"supplier": "تامین‌کننده متعلق به این فروشگاه نیست."})
    if not items:
        raise ValidationError({"items": "دست‌کم یک کالا به فاکتور اضافه کنید."})
    products = {p.pk: p for p in ShopProduct.objects.filter(store=store, pk__in=[i["product"] for i in items])}
    lines = []
    for it in items:
        p = products.get(it["product"])
        qty, cost = int(it["qty"]), int(it["unit_cost"])
        if not p:
            raise ValidationError({"items": "کالا یافت نشد یا متعلق به این فروشگاه نیست."})
        if qty <= 0 or cost <= 0:
            raise ValidationError({"items": f"تعداد و قیمت خرید «{p.name}» باید بیشتر از صفر باشد."})
        lines.append((p, qty, cost))
    goods = sum(q * c for _, q, c in lines)
    if goods > 10**13 or max(discount, tax, shipping) > 10**13:
        raise ValidationError({"items": "مبلغ فاکتور از حد مجاز بیشتر است؛ تعداد و قیمت‌ها را بررسی کنید."})
    total = goods - discount + tax + shipping
    if total < 0:
        raise ValidationError({"discount": "تخفیف از جمع فاکتور بیشتر است."})
    if paid < 0 or paid > total:
        raise ValidationError({"paid": "مبلغ پرداختی نمی‌تواند از جمع فاکتور بیشتر باشد."})

    inv = PurchaseInvoice.objects.create(
        store=store, supplier=supplier, number=number[:40], date=date, note=note[:300], discount=discount, tax=tax,
        shipping=shipping, total=total, created_by=by,
    )
    extra = shipping - discount        # حمل (+) و تخفیف (−) به نسبت ارزش هر ردیف در قیمت تمام‌شده می‌نشیند
    for p, qty, cost in lines:
        PurchaseItem.objects.create(invoice=inv, product=p, qty=qty, unit_cost=cost)
        share = Decimal(extra) * (qty * cost) / goods if goods else Decimal(0)
        landed = max(1, _round(Decimal(qty * cost + share) / qty))
        record(p.pk, qty, Kind.PURCHASE, ref=f"PI{inv.pk}", unit_cost=landed, by=by,
               note=f"فاکتور خرید {number or inv.pk} — {supplier.name}")
    if paid:
        SupplierPayment.objects.create(store=store, supplier=supplier, invoice=inv, amount=paid, date=date, note="پرداخت هنگام ثبت فاکتور")
    return inv


@transaction.atomic
def pay_supplier(store, supplier: Supplier, amount: int, *, date: date_cls, invoice: PurchaseInvoice | None = None,
                 method: str = "", note: str = "") -> SupplierPayment:
    if supplier.store_id != store.pk:
        raise ValidationError({"supplier": "تامین‌کننده متعلق به این فروشگاه نیست."})
    if amount <= 0:
        raise ValidationError({"amount": "مبلغ باید بیشتر از صفر باشد."})
    return SupplierPayment.objects.create(store=store, supplier=supplier, invoice=invoice, amount=amount, date=date,
                                          method=method[:30], note=note[:200])
