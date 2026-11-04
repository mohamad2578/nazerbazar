"""انبارداری، حسابداری و فاکتور فروشگاه ویژه.

همه داده‌ها به یک فروشگاه (store) وابسته‌اند و فقط مالک همان فروشگاه ویژه به آن‌ها دسترسی دارد.
مبلغ‌ها همه به ریال ذخیره می‌شوند.
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class StoreSettings(TimeStamped):
    """تنظیمات مالی، فاکتور و درگاه پرداخت یک فروشگاه ویژه."""

    class Gateway(models.TextChoices):
        NONE = "", "درگاه پیش‌فرض سامانه"
        ZARINPAL = "zarinpal", "زرین‌پال"
        ZIBAL = "zibal", "زیبال"

    store = models.OneToOneField("orgs.Store", on_delete=models.CASCADE, related_name="finance")
    # مالیات و ارسال
    vat_percent = models.PositiveSmallIntegerField("مالیات بر ارزش افزوده (٪)", default=0)
    delivery_fee = models.PositiveBigIntegerField("هزینه ارسال با پیک (ریال)", default=0)
    free_delivery_over = models.PositiveBigIntegerField("ارسال رایگان برای خرید بالاتر از (ریال)", null=True, blank=True)
    # مشخصات فاکتور
    economic_code = models.CharField("کد اقتصادی", max_length=20, blank=True)
    national_id = models.CharField("شناسه ملی / کد ملی", max_length=20, blank=True)
    postal_code = models.CharField("کد پستی", max_length=10, blank=True)
    invoice_prefix = models.CharField("پیشوند شماره فاکتور", max_length=8, default="F")
    invoice_footer = models.CharField("پاورقی فاکتور", max_length=300, blank=True)
    invoice_seq = models.PositiveIntegerField(default=0)
    # درگاه پرداخت اختصاصی این فروشگاه (واریز مستقیم به حساب خود فروشگاه)
    gateway_provider = models.CharField("درگاه پرداخت", max_length=10, choices=Gateway.choices, blank=True, default="")
    gateway_merchant = models.CharField("کد پذیرنده درگاه", max_length=64, blank=True)
    gateway_sandbox = models.BooleanField("حالت آزمایشی درگاه", default=False)
    gateway_active = models.BooleanField("درگاه اختصاصی فعال", default=False)

    class Meta:
        verbose_name = "تنظیمات مالی فروشگاه"
        verbose_name_plural = "تنظیمات مالی فروشگاه‌ها"

    @property
    def own_gateway(self) -> bool:
        return bool(self.gateway_active and self.gateway_provider and self.gateway_merchant)


class Supplier(TimeStamped):
    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField("نام تامین‌کننده", max_length=150)
    phone = models.CharField("تلفن", max_length=20, blank=True)
    address = models.CharField("نشانی", max_length=300, blank=True)
    note = models.CharField("یادداشت", max_length=300, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "تامین‌کننده"
        verbose_name_plural = "تامین‌کنندگان"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    """دفتر حرکت کالا؛ هر تغییر موجودی یک ردیف دارد و موجودی پس از آن (balance_after) ثبت می‌شود."""

    class Kind(models.TextChoices):
        OPENING = "opening", "موجودی اولیه"
        PURCHASE = "purchase", "خرید از تامین‌کننده"
        SALE = "sale", "فروش"
        SALE_CANCEL = "sale_cancel", "بازگشت از لغو سفارش"
        ADJUST = "adjust", "تعدیل / انبارگردانی"
        DAMAGE = "damage", "ضایعات / خرابی"
        SUPPLIER_RETURN = "supplier_return", "برگشت به تامین‌کننده"

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="stock_movements")
    product = models.ForeignKey("shop.ShopProduct", on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    qty = models.IntegerField("تعداد (منفی = خروج)")
    unit_cost = models.PositiveBigIntegerField("قیمت تمام‌شده واحد (ریال)", default=0)
    balance_after = models.IntegerField()
    ref = models.CharField("مرجع", max_length=40, blank=True)
    note = models.CharField(max_length=200, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "حرکت انبار"
        verbose_name_plural = "حرکات انبار"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["store", "created_at"]), models.Index(fields=["product", "created_at"])]


class PurchaseInvoice(TimeStamped):
    """فاکتور خرید از تامین‌کننده؛ با ثبت، موجودی انبار زیاد و قیمت تمام‌شده (میانگین موزون) به‌روز می‌شود."""

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="purchase_invoices")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField("شماره فاکتور تامین‌کننده", max_length=40, blank=True)
    date = models.DateField("تاریخ فاکتور")
    note = models.CharField(max_length=300, blank=True)
    discount = models.PositiveBigIntegerField("تخفیف (ریال)", default=0)
    tax = models.PositiveBigIntegerField("مالیات (ریال)", default=0)
    shipping = models.PositiveBigIntegerField("هزینه حمل (ریال)", default=0)
    total = models.PositiveBigIntegerField("جمع کل (ریال)", default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "فاکتور خرید"
        verbose_name_plural = "فاکتورهای خرید"
        ordering = ["-date", "-id"]


class PurchaseItem(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("shop.ShopProduct", on_delete=models.PROTECT, related_name="purchase_items")
    qty = models.PositiveIntegerField()
    unit_cost = models.PositiveBigIntegerField("قیمت خرید واحد (ریال)")

    @property
    def line_total(self) -> int:
        return self.qty * self.unit_cost


class SupplierPayment(models.Model):
    """پرداخت به تامین‌کننده (تسویه بدهی)."""

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="supplier_payments")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    invoice = models.ForeignKey(PurchaseInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.PositiveBigIntegerField("مبلغ (ریال)")
    date = models.DateField("تاریخ پرداخت")
    method = models.CharField("روش", max_length=30, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]


class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = "rent", "اجاره"
        SALARY = "salary", "حقوق و دستمزد"
        PACKAGING = "packaging", "بسته‌بندی"
        TRANSPORT = "transport", "حمل و نقل"
        MARKETING = "marketing", "تبلیغات"
        UTILITY = "utility", "قبوض و انرژی"
        OTHER = "other", "سایر"

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField("دسته", max_length=12, choices=Category.choices, default=Category.OTHER)
    amount = models.PositiveBigIntegerField("مبلغ (ریال)")
    date = models.DateField("تاریخ")
    note = models.CharField("شرح", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "هزینه"
        verbose_name_plural = "هزینه‌ها"
        ordering = ["-date", "-id"]


class CourierSettlement(models.Model):
    """تسویه با پیک: تحویل وجه نقد دریافتی به فروشگاه، یا پرداخت کارمزد پیک."""

    class Kind(models.TextChoices):
        CASH_HANDOVER = "cash", "تحویل وجه نقد به فروشگاه"
        FEE_PAYOUT = "fee", "پرداخت کارمزد به پیک"

    courier = models.ForeignKey("shop.Courier", on_delete=models.CASCADE, related_name="settlements")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    amount = models.PositiveBigIntegerField("مبلغ (ریال)")
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
