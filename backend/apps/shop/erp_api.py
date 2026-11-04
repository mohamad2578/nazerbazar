"""API انبارداری و حسابداری فروشگاه ویژه (فقط برای مالک فروشگاهی که «ویژه» است)."""
import csv
from datetime import date

from django.conf import settings
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from . import erp_reports, inventory
from .erp import Expense, PurchaseInvoice, PurchaseItem, StockMovement, StoreSettings, Supplier, SupplierPayment
from .models import ShopProduct


def featured_store(request):
    """فروشگاه ویژه‌ی فعالِ کاربر؛ در غیر این صورت ۴۰۳."""
    u = request.user
    store = u.stores.first() if u.is_authenticated and u.role == "store" else None
    if not store or not store.is_featured or store.status != "active":
        raise PermissionDenied("این بخش فقط برای مالک فروشگاه ویژه است.")
    return store


class FeaturedOwner(BasePermission):
    def has_permission(self, request, view):
        try:
            featured_store(request)
        except PermissionDenied:
            return False
        return True


MAX_MONEY = 10**13          # ۱ هزار میلیارد تومان؛ بالاتر از این قطعا خطای ورودی است
MAX_QTY = 10**8


def _int(v, field: str, default: int | None = 0, minimum: int = 0, maximum: int = MAX_MONEY) -> int:
    if v in (None, ""):
        if default is None:
            raise ValidationError({field: "این فیلد الزامی است."})
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValidationError({field: "عدد صحیح وارد کنید."})
    if n < minimum or n > maximum:
        raise ValidationError({field: "مقدار نامعتبر است."})
    return n


def _date(v, field: str = "date") -> date:
    try:
        return date.fromisoformat(str(v)[:10]) if v else date.today()
    except ValueError:
        raise ValidationError({field: "تاریخ نامعتبر است."})


# ───────────────────────── تنظیمات مالی ─────────────────────────


class SettingsSerializer(serializers.ModelSerializer):
    own_gateway = serializers.BooleanField(read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_address = serializers.CharField(source="store.address", read_only=True)
    store_phone = serializers.CharField(source="store.phone", read_only=True)
    next_invoice = serializers.SerializerMethodField()

    class Meta:
        model = StoreSettings
        fields = [
            "vat_percent", "delivery_fee", "free_delivery_over", "economic_code", "national_id", "postal_code",
            "invoice_prefix", "invoice_footer", "gateway_provider", "gateway_merchant", "gateway_sandbox",
            "gateway_active", "own_gateway", "store_name", "store_address", "store_phone", "next_invoice",
        ]

    def get_next_invoice(self, s):
        return f"{s.invoice_prefix or 'F'}{s.invoice_seq + 1:06d}"

    def validate(self, a):
        vat = a.get("vat_percent", getattr(self.instance, "vat_percent", 0))
        if vat > 30:
            raise serializers.ValidationError({"vat_percent": "درصد مالیات باید بین ۰ تا ۳۰ باشد."})
        provider = a.get("gateway_provider", getattr(self.instance, "gateway_provider", ""))
        merchant = a.get("gateway_merchant", getattr(self.instance, "gateway_merchant", ""))
        active = a.get("gateway_active", getattr(self.instance, "gateway_active", False))
        if active and not (provider and merchant.strip()):
            raise serializers.ValidationError({"gateway_merchant": "برای فعال‌سازی درگاه، نوع درگاه و کد پذیرنده را وارد کنید."})
        sandbox = a.get("gateway_sandbox", getattr(self.instance, "gateway_sandbox", False))
        if active and not (settings.DEBUG or settings.PAYMENT_ALLOW_MOCK) and (
            sandbox or (provider == "zibal" and merchant.strip().lower() == "zibal")
        ):
            raise serializers.ValidationError({"gateway_merchant": "کد آزمایشی یا حالت sandbox روی سامانه واقعی پذیرفته نمی‌شود؛ کد پذیرنده واقعی را وارد کنید."})
        return a


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def settings_view(request):
    s = inventory.get_settings(featured_store(request))
    if request.method == "PATCH":
        ser = SettingsSerializer(s, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(SettingsSerializer(s).data)


# ───────────────────────── داشبورد و گزارش‌ها ─────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def dashboard_view(request):
    return Response(erp_reports.dashboard(featured_store(request)))


@api_view(["GET"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def sales_report_view(request):
    start, end = erp_reports.parse_range(request.query_params)
    return Response(erp_reports.sales_report(featured_store(request), start, end))


# ───────────────────────── موجودی انبار ─────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def inventory_list(request):
    store = featured_store(request)
    rows = erp_reports.inventory_rows(store, request.query_params.get("q", ""), request.query_params.get("status", ""))
    return Response({
        "results": rows,
        "summary": {
            "items": len(rows), "cost_value": sum(r["value"] for r in rows), "sale_value": sum(r["sale_value"] for r in rows),
            "low": sum(1 for r in rows if r["status"] == "low"), "out": sum(1 for r in rows if r["status"] == "out"),
        },
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def inventory_update(request, pk):
    """ویرایش مشخصات انبارداری کالا: کد کالا، حد سفارش مجدد، محل قفسه و (دستی) قیمت تمام‌شده."""
    p = get_object_or_404(ShopProduct, pk=pk, store=featured_store(request))
    d = request.data
    if "sku" in d:
        p.sku = str(d["sku"]).strip()[:40]
    if "shelf" in d:
        p.shelf = str(d["shelf"]).strip()[:40]
    if "min_stock" in d:
        p.min_stock = _int(d["min_stock"], "min_stock", maximum=MAX_QTY)
    if "cost_price" in d:
        p.cost_price = _int(d["cost_price"], "cost_price")
    p.save(update_fields=["sku", "shelf", "min_stock", "cost_price", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def inventory_adjust(request, pk):
    """تعدیل موجودی: {mode: set|delta, value, kind: adjust|damage|supplier_return|opening, note}"""
    p = get_object_or_404(ShopProduct, pk=pk, store=featured_store(request))
    d = request.data
    value = _int(d.get("value"), "value", default=None, minimum=-MAX_QTY, maximum=MAX_QTY)
    kind = d.get("kind") or StockMovement.Kind.ADJUST
    note = (d.get("note") or "").strip()
    if kind in (StockMovement.Kind.DAMAGE, StockMovement.Kind.SUPPLIER_RETURN) and not note:
        raise ValidationError({"note": "برای ضایعات یا برگشت به تامین‌کننده، دلیل را بنویسید."})
    if d.get("mode") == "set":
        mv = inventory.adjust(p, set_to=value, kind=kind, note=note, by=request.user)
    else:
        mv = inventory.adjust(p, delta=value, kind=kind, note=note, by=request.user)
    p.refresh_from_db()
    return Response({"stock": p.stock, "movement": mv.pk if mv else None})


class MovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "kind", "kind_display", "qty", "unit_cost", "balance_after", "ref", "note",
                  "by_name", "created_at"]

    def get_by_name(self, m):
        return (m.by.full_name or m.by.mobile) if m.by_id else ""


class MovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """دفتر حرکت کالا (ورود و خروج انبار) با فیلتر کالا، نوع و بازه تاریخ."""

    serializer_class = MovementSerializer
    permission_classes = [IsAuthenticated, FeaturedOwner]

    def get_queryset(self):
        qs = StockMovement.objects.filter(store=featured_store(self.request)).select_related("product", "by")
        q = self.request.query_params
        if q.get("product"):
            qs = qs.filter(product_id=_int(q["product"], "product", maximum=2**31 - 1))
        if q.get("kind"):
            qs = qs.filter(kind=q["kind"])
        if q.get("from"):
            qs = qs.filter(created_at__date__gte=_date(q["from"], "from"))
        if q.get("to"):
            qs = qs.filter(created_at__date__lte=_date(q["to"], "to"))
        return qs


# ───────────────────────── تامین‌کنندگان و فاکتور خرید ─────────────────────────


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "address", "note", "is_active"]


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, FeaturedOwner]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return Supplier.objects.filter(store=featured_store(self.request))

    def perform_create(self, serializer):
        serializer.save(store=featured_store(self.request))

    def list(self, request, *args, **kwargs):
        bal = erp_reports.supplier_balances(featured_store(request))
        data = SupplierSerializer(self.get_queryset(), many=True).data
        for r in data:
            r.update(bal.get(r["id"], {"purchased": 0, "paid": 0, "balance": 0}))
        return Response(data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """پرداخت به تامین‌کننده (تسویه بدهی)؛ amount به ریال."""
        store = featured_store(request)
        sup = self.get_object()
        d = request.data
        inv = (PurchaseInvoice.objects.filter(pk=_int(d.get("invoice"), "invoice", maximum=2**31 - 1), store=store, supplier=sup).first()
               if d.get("invoice") else None)
        pay = inventory.pay_supplier(store, sup, _int(d.get("amount"), "amount", default=None, minimum=1), date=_date(d.get("date")),
                                     invoice=inv, method=d.get("method") or "", note=d.get("note") or "")
        return Response({"id": pay.pk, **erp_reports.supplier_balances(store)[sup.pk]}, status=201)

    @action(detail=True)
    def ledger(self, request, pk=None):
        """صورت‌حساب تامین‌کننده: فاکتورها و پرداخت‌ها به ترتیب تاریخ."""
        sup = self.get_object()
        rows = [{"type": "invoice", "id": i.pk, "date": i.date, "amount": i.total, "label": f"فاکتور خرید {i.number or i.pk}"}
                for i in sup.invoices.all()]
        rows += [{"type": "payment", "id": p.pk, "date": p.date, "amount": -p.amount, "label": f"پرداخت {p.method or ''} {p.note}".strip()}
                 for p in sup.payments.all()]
        rows.sort(key=lambda r: (r["date"], r["id"]))
        bal = 0
        for r in rows:
            bal += r["amount"]
            r["balance"] = bal
        return Response({"rows": rows[::-1], "balance": bal})


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseItem
        fields = ["id", "product", "product_name", "qty", "unit_cost", "line_total"]


class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    paid = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseInvoice
        fields = ["id", "supplier", "supplier_name", "number", "date", "note", "discount", "tax", "shipping", "total", "paid", "items",
                  "created_at"]

    def get_paid(self, inv):
        return sum(p.amount for p in inv.payments.all())


class PurchaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """فاکتورهای خرید؛ ثبت فاکتور موجودی را زیاد و قیمت تمام‌شده را به‌روز می‌کند (ویرایش ندارد؛ اصلاح با تعدیل انبار)."""

    serializer_class = PurchaseSerializer
    permission_classes = [IsAuthenticated, FeaturedOwner]

    def get_queryset(self):
        qs = PurchaseInvoice.objects.filter(store=featured_store(self.request)).select_related("supplier").prefetch_related(
            "items__product", "payments")
        q = self.request.query_params
        if q.get("supplier"):
            qs = qs.filter(supplier_id=_int(q["supplier"], "supplier", maximum=2**31 - 1))
        if q.get("search"):
            qs = qs.filter(Q(number__icontains=q["search"]) | Q(supplier__name__icontains=q["search"]))
        return qs

    def create(self, request):
        store = featured_store(request)
        d = request.data
        supplier = get_object_or_404(Supplier, pk=_int(d.get("supplier"), "supplier", default=None, maximum=2**31 - 1), store=store)
        raw = d.get("items") or []
        if not isinstance(raw, list) or not all(isinstance(i, dict) for i in raw) or len(raw) > 200:
            raise ValidationError({"items": "فهرست اقلام نامعتبر است."})
        items = [{"product": _int(i.get("product"), "items", default=None),
                  "qty": _int(i.get("qty"), "items", default=None, minimum=1, maximum=MAX_QTY),
                  "unit_cost": _int(i.get("unit_cost"), "items", default=None, minimum=1)} for i in raw]
        inv = inventory.create_purchase(
            store, supplier, items, date=_date(d.get("date")), number=str(d.get("number") or "").strip(),
            note=str(d.get("note") or "").strip(), discount=_int(d.get("discount"), "discount"), tax=_int(d.get("tax"), "tax"),
            shipping=_int(d.get("shipping"), "shipping"), paid=_int(d.get("paid"), "paid"), by=request.user,
        )
        return Response(PurchaseSerializer(self.get_queryset().get(pk=inv.pk)).data, status=201)


# ───────────────────────── هزینه‌ها ─────────────────────────


class ExpenseSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "category", "category_display", "amount", "date", "note"]

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("مبلغ باید بیشتر از صفر باشد.")
        return v


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, FeaturedOwner]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Expense.objects.filter(store=featured_store(self.request))
        q = self.request.query_params
        if q.get("category"):
            qs = qs.filter(category=q["category"])
        if q.get("from"):
            qs = qs.filter(date__gte=_date(q["from"], "from"))
        if q.get("to"):
            qs = qs.filter(date__lte=_date(q["to"], "to"))
        return qs

    def perform_create(self, serializer):
        serializer.save(store=featured_store(self.request), created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        resp = super().list(request, *args, **kwargs)
        resp.data["total"] = self.filter_queryset(self.get_queryset()).aggregate(v=Sum("amount"))["v"] or 0
        return resp


# ───────────────────────── خروجی CSV ─────────────────────────


class _SafeWriter:
    """سلول متنی که با = + - @ شروع شود در اکسل «فرمول» حساب می‌شود؛ با یک نقل‌قول خنثی‌اش می‌کنیم."""

    def __init__(self, w):
        self.w = w

    @staticmethod
    def _cell(v):
        return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

    def writerow(self, row):
        self.w.writerow([self._cell(v) for v in row])


@api_view(["GET"])
@permission_classes([IsAuthenticated, FeaturedOwner])
def export_csv(request, name):
    """خروجی CSV (UTF-8 با BOM برای اکسل): sales | inventory | movements | expenses | purchases"""
    store = featured_store(request)
    start, end = erp_reports.parse_range(request.query_params)
    out = HttpResponse(content_type="text/csv; charset=utf-8")
    out["Content-Disposition"] = f'attachment; filename="{name}-{start}-{end}.csv"'
    out.write("﻿")
    w = _SafeWriter(csv.writer(out))
    if name == "sales":
        rep = erp_reports.sales_report(store, start, end)
        w.writerow(["تاریخ", "تعداد سفارش", "درآمد کالا (ریال)", "بهای تمام‌شده (ریال)", "سود ناخالص (ریال)"])
        for r in rep["series"]:
            w.writerow([r["date"], r["orders"], r["revenue"], r["cogs"], r["profit"]])
        w.writerow([])
        w.writerow(["کالا", "تعداد فروش", "درآمد (ریال)", "بهای تمام‌شده (ریال)", "سود (ریال)", "حاشیه سود ٪"])
        for r in rep["by_product"]:
            w.writerow([r["name"], r["qty"], r["revenue"], r["cost"], r["profit"], r["margin"]])
    elif name == "inventory":
        w.writerow(["کالا", "برند", "کد کالا", "قفسه", "موجودی", "حد سفارش", "قیمت تمام‌شده", "قیمت فروش", "ارزش موجودی (تمام‌شده)", "وضعیت"])
        for r in erp_reports.inventory_rows(store):
            w.writerow([r["name"], r["brand"], r["sku"], r["shelf"], r["stock"] if r["stock"] is not None else "نامحدود", r["min_stock"],
                        r["cost_price"], r["price"], r["value"], r["status"]])
    elif name == "movements":
        w.writerow(["زمان", "کالا", "نوع", "تعداد", "قیمت واحد", "موجودی پس از حرکت", "مرجع", "توضیح"])
        for m in StockMovement.objects.filter(store=store, created_at__date__gte=start, created_at__date__lte=end).select_related("product"):
            w.writerow([m.created_at.strftime("%Y-%m-%d %H:%M"), m.product.name, m.get_kind_display(), m.qty, m.unit_cost, m.balance_after,
                        m.ref, m.note])
    elif name == "expenses":
        w.writerow(["تاریخ", "دسته", "مبلغ (ریال)", "شرح"])
        for e in Expense.objects.filter(store=store, date__gte=start, date__lte=end):
            w.writerow([e.date, e.get_category_display(), e.amount, e.note])
    elif name == "purchases":
        w.writerow(["تاریخ", "شماره", "تامین‌کننده", "جمع (ریال)", "پرداخت‌شده (ریال)"])
        for i in PurchaseInvoice.objects.filter(store=store, date__gte=start, date__lte=end).select_related("supplier").prefetch_related("payments"):
            w.writerow([i.date, i.number, i.supplier.name, i.total, sum(p.amount for p in i.payments.all())])
    else:
        raise ValidationError({"detail": "گزارش نامعتبر است."})
    return out
