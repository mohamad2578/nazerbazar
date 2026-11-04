"""گزارش‌های حسابداری و انبار فروشگاه ویژه (سود و زیان، فروش، موجودی، بدهی تامین‌کنندگان، حساب پیک‌ها).

تعریف‌ها:
  • فروش = سفارش‌های «تحویل‌شده» در بازه (بر اساس زمان تحویل)
  • درآمد کالا = مجموع (قیمت × تعداد) اقلام منهای تخفیف بسته‌ها (بدون مالیات و هزینه ارسال)
  • بهای تمام‌شده (COGS) = مجموع (قیمت تمام‌شده در لحظه فروش × تعداد)
  • سود ناخالص = درآمد کالا − بهای تمام‌شده
  • سود خالص = سود ناخالص + درآمد ارسال − کارمزد پیک − هزینه‌ها
مالیات ارزش افزوده بخشی از درآمد نیست (به‌عنوان بدهی مالیاتی جدا گزارش می‌شود).
"""
from datetime import date, timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from .commerce import Courier
from .erp import CourierSettlement, Expense, PurchaseInvoice, StockMovement, Supplier, SupplierPayment
from .models import ShopProduct
from .orders import Order, OrderItem


def parse_range(params, default_days: int = 30) -> tuple[date, date]:
    """بازه گزارش از ?from=YYYY-MM-DD&to=YYYY-MM-DD؛ پیش‌فرض ۳۰ روز اخیر."""
    today = timezone.localdate()

    def _d(v, d):
        try:
            return date.fromisoformat(v) if v else d
        except ValueError:
            return d

    end = _d(params.get("to"), today)
    start = _d(params.get("from"), end - timedelta(days=default_days - 1))
    if start > end:
        start, end = end, start
    if (end - start).days > 400:               # جلوگیری از گزارش چندساله که سرور را سنگین می‌کند
        start = end - timedelta(days=400)
    return start, end


def _delivered(store, start: date, end: date):
    return Order.objects.filter(store=store, status=Order.Status.DELIVERED, delivered_at__date__gte=start,
                                delivered_at__date__lte=end)


def _sum(qs, expr) -> int:
    return qs.aggregate(v=Coalesce(Sum(expr), 0))["v"] or 0


LINE = ExpressionWrapper(F("price") * F("quantity"), output_field=IntegerField())
COST = ExpressionWrapper(F("cost_price") * F("quantity"), output_field=IntegerField())


def sales_report(store, start: date, end: date) -> dict:
    orders = _delivered(store, start, end)
    items = OrderItem.objects.filter(order__in=orders)
    gross = _sum(items, LINE)
    discount = _sum(orders, "discount")
    revenue = gross - discount
    cogs = _sum(items, COST)
    delivery_income = _sum(orders, "delivery_fee")
    courier_cost = _sum(orders, "courier_fee")
    tax = _sum(orders, "tax")
    expenses = _sum(Expense.objects.filter(store=store, date__gte=start, date__lte=end), "amount")
    purchases = _sum(PurchaseInvoice.objects.filter(store=store, date__gte=start, date__lte=end), "total")
    gross_profit = revenue - cogs
    net = gross_profit + delivery_income - courier_cost - expenses
    n = orders.count()

    daily = {}
    for row in orders.annotate(d=TruncDate("delivered_at")).values("d").annotate(
        orders=Count("pk"), total=Sum("total"), tax=Sum("tax"), fee=Sum("delivery_fee"), disc=Sum("discount"),
    ):
        daily[row["d"]] = row
    per_day = {
        r["d"]: r for r in items.annotate(d=TruncDate("order__delivered_at")).values("d").annotate(c=Sum(COST), g=Sum(LINE))
    }
    series = []
    d = start
    while d <= end:
        r = daily.get(d)
        pd = per_day.get(d)
        rev = ((pd["g"] if pd else 0) - r["disc"]) if r else 0
        cg = (pd["c"] if pd else 0) if r else 0
        series.append({"date": d.isoformat(), "orders": r["orders"] if r else 0, "revenue": rev, "cogs": cg, "profit": rev - cg})
        d += timedelta(days=1)

    by_product = list(
        items.values("name").annotate(qty=Sum("quantity"), revenue=Sum(LINE), cost=Sum(COST)).order_by("-revenue")[:50]
    )
    for r in by_product:
        r["profit"] = r["revenue"] - r["cost"]
        r["margin"] = round(r["profit"] / r["revenue"] * 100, 1) if r["revenue"] else 0
    by_method = list(orders.values("payment_method").annotate(count=Count("pk"), total=Sum("total")).order_by("-total"))
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "totals": {
            "orders": n, "gross": gross, "discount": discount, "revenue": revenue, "cogs": cogs, "gross_profit": gross_profit,
            "margin": round(gross_profit / revenue * 100, 1) if revenue else 0, "delivery_income": delivery_income,
            "courier_cost": courier_cost, "expenses": expenses, "net_profit": net, "tax": tax, "purchases": purchases,
            "avg_order": round((revenue + delivery_income + tax) / n) if n else 0,
        },
        "series": series, "by_product": by_product, "by_method": by_method,
        "expenses_by_category": list(
            Expense.objects.filter(store=store, date__gte=start, date__lte=end).values("category").annotate(total=Sum("amount")).order_by("-total")
        ),
    }


def inventory_status(p: ShopProduct) -> str:
    if p.stock is None:
        return "unlimited"
    if p.stock <= 0:
        return "out"
    if p.min_stock and p.stock <= p.min_stock:
        return "low"
    return "ok"


def inventory_rows(store, q: str = "", status: str = "") -> list[dict]:
    since = timezone.now() - timedelta(days=30)
    sold = dict(
        StockMovement.objects.filter(store=store, kind=StockMovement.Kind.SALE, created_at__gte=since)
        .values_list("product").annotate(n=Sum("qty"))
    )
    qs = ShopProduct.objects.filter(store=store, is_active=True).order_by("name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q))
    rows = []
    for p in qs:
        st = inventory_status(p)
        if status and st != status:
            continue
        stock = p.stock or 0
        rows.append({
            "id": p.pk, "name": p.name, "brand": p.brand, "sku": p.sku, "shelf": p.shelf, "image": p.image.url if p.image else None,
            "unit_display": p.get_unit_display(), "stock": p.stock, "min_stock": p.min_stock, "cost_price": p.cost_price,
            "price": p.price, "value": stock * p.cost_price, "sale_value": stock * p.price, "status": st,
            "sold_30d": abs(sold.get(p.pk, 0)),
            "margin": round((p.price - p.cost_price) / p.price * 100, 1) if p.price and p.cost_price else None,
        })
    return rows


def supplier_balances(store) -> dict[int, dict]:
    inv = dict(PurchaseInvoice.objects.filter(store=store).values_list("supplier").annotate(t=Sum("total")))
    pay = dict(SupplierPayment.objects.filter(store=store).values_list("supplier").annotate(t=Sum("amount")))
    out = {}
    for s in Supplier.objects.filter(store=store):
        b, p = inv.get(s.pk, 0), pay.get(s.pk, 0)
        out[s.pk] = {"purchased": b, "paid": p, "balance": b - p}
    return out


def courier_ledger(courier: Courier) -> dict:
    """حساب پیک: وجه نقد دردست و کارمزد پرداخت‌نشده."""
    delivered = Order.objects.filter(courier=courier, status=Order.Status.DELIVERED)
    cash_collected = _sum(delivered.filter(payment_method=Order.Payment.CASH), "total")
    cash_handed = _sum(courier.settlements.filter(kind=CourierSettlement.Kind.CASH_HANDOVER), "amount")
    fee_earned = _sum(delivered, "courier_fee")
    fee_paid = _sum(courier.settlements.filter(kind=CourierSettlement.Kind.FEE_PAYOUT), "amount")
    return {
        "deliveries": delivered.count(), "cash_collected": cash_collected, "cash_handed": cash_handed,
        "cash_on_hand": cash_collected - cash_handed, "fee_earned": fee_earned, "fee_paid": fee_paid,
        "fee_due": fee_earned - fee_paid,
    }


def dashboard(store) -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    day = sales_report(store, today, today)["totals"]
    month = sales_report(store, month_start, today)["totals"]
    inv = inventory_rows(store)
    pending = Order.objects.filter(store=store, status__in=(Order.Status.NEW, Order.Status.CONFIRMED, Order.Status.PREPARING)).count()
    ready = Order.objects.filter(store=store, status=Order.Status.READY).count()
    on_road = Order.objects.filter(store=store, status=Order.Status.OUT_FOR_DELIVERY).count()
    balances = supplier_balances(store)
    cash_with_couriers = sum(courier_ledger(c)["cash_on_hand"] for c in Courier.objects.filter(store=store))
    low = [r for r in inv if r["status"] in ("low", "out")]
    return {
        "today": day, "month": month,
        "pending_orders": pending, "ready_orders": ready, "on_road_orders": on_road,
        "stock_value": sum(r["value"] for r in inv), "stock_sale_value": sum(r["sale_value"] for r in inv),
        "low_stock": sum(1 for r in inv if r["status"] == "low"), "out_of_stock": sum(1 for r in inv if r["status"] == "out"),
        "low_items": [{"id": r["id"], "name": r["name"], "stock": r["stock"], "min_stock": r["min_stock"], "status": r["status"]} for r in low[:8]],
        "payables": sum(max(0, b["balance"]) for b in balances.values()),
        "cash_with_couriers": cash_with_couriers,
        "top_products": sales_report(store, month_start, today)["by_product"][:5],
        "series": sales_report(store, today - timedelta(days=13), today)["series"],
    }
