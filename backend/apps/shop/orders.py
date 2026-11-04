"""سفارش‌های فروشگاه اینترنتی.

مشتری از ویترین یک فروشگاه سبد می‌بندد و سفارش ثبت می‌کند؛ سفارش بلافاصله در
کارتابل همان فروشگاه («سفارش‌ها») می‌نشیند و فروشنده آن را تایید/آماده/تحویل می‌کند.
پرداخت آنلاین در این مرحله وجود ندارد: تسویه حضوری یا هنگام تحویل است.
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class Order(TimeStamped):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "در انتظار پرداخت"
        NEW = "new", "ثبت شده"
        CONFIRMED = "confirmed", "تایید فروشگاه"
        PREPARING = "preparing", "در حال آماده‌سازی"
        READY = "ready", "آماده تحویل"
        OUT_FOR_DELIVERY = "out_for_delivery", "در مسیر تحویل"
        DELIVERED = "delivered", "تحویل شد"
        CANCELED = "canceled", "لغو شد"

    class Delivery(models.TextChoices):
        PICKUP = "pickup", "دریافت حضوری از فروشگاه"
        DELIVERY = "delivery", "ارسال به نشانی مشتری"

    class Payment(models.TextChoices):
        ONLINE = "online", "پرداخت اینترنتی"
        CASH = "cash", "پرداخت نقدی هنگام تحویل"
        WALLET = "wallet", "کیف پول"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "پرداخت‌نشده"
        PAID = "paid", "پرداخت‌شده"
        REFUNDED = "refunded", "بازگشت به کیف پول"

    OPEN_STATUSES = (Status.AWAITING_PAYMENT, Status.NEW, Status.CONFIRMED, Status.PREPARING, Status.READY,
                     Status.OUT_FOR_DELIVERY)

    code = models.CharField("کد سفارش", max_length=12, unique=True)
    store = models.ForeignKey("orgs.Store", on_delete=models.PROTECT, related_name="orders", verbose_name="فروشگاه")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="مشتری"
    )
    customer_name = models.CharField("نام مشتری", max_length=120)
    customer_phone = models.CharField("تلفن تماس", max_length=15)
    delivery = models.CharField("نحوه تحویل", max_length=10, choices=Delivery.choices, default=Delivery.PICKUP)
    address = models.CharField("نشانی تحویل", max_length=300, blank=True)
    note = models.TextField("توضیحات مشتری", blank=True)
    total = models.PositiveBigIntegerField("مبلغ کل (ریال)", default=0)
    lat = models.DecimalField("عرض جغرافیایی تحویل", max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField("طول جغرافیایی تحویل", max_digits=9, decimal_places=6, null=True, blank=True)
    courier = models.ForeignKey("shop.Courier", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="orders", verbose_name="پیک")
    assigned_at = models.DateTimeField("زمان ارسال به پیک", null=True, blank=True)
    picked_at = models.DateTimeField("زمان تحویل به پیک", null=True, blank=True)
    delivered_at = models.DateTimeField("زمان تحویل به مشتری", null=True, blank=True)
    discount = models.PositiveBigIntegerField("تخفیف بسته‌ها (ریال)", default=0)
    tax = models.PositiveBigIntegerField("مالیات بر ارزش افزوده (ریال)", default=0)
    delivery_fee = models.PositiveBigIntegerField("هزینه ارسال (ریال)", default=0)
    courier_fee = models.PositiveBigIntegerField("کارمزد پیک (ریال)", default=0)
    invoice_no = models.CharField("شماره فاکتور", max_length=24, blank=True, db_index=True)
    payment_method = models.CharField("روش پرداخت", max_length=10, choices=Payment.choices, default=Payment.CASH)
    payment_status = models.CharField("وضعیت پرداخت", max_length=10, choices=PaymentStatus.choices,
                                      default=PaymentStatus.UNPAID, db_index=True)
    status = models.CharField("وضعیت", max_length=16, choices=Status.choices, default=Status.NEW, db_index=True)
    store_note = models.TextField("پاسخ/یادداشت فروشگاه", blank=True)
    closed_at = models.DateTimeField("زمان بسته شدن", null=True, blank=True)

    SCOPE = {
        "province": ("store__union__chamber__county__province", "store__covered_unions__chamber__county__province"),
        "chamber": ("store__union__chamber", "store__covered_unions__chamber"),
        "union": ("store__union", "store__covered_unions"),
        "store": "store",
    }

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "status"])]

    def __str__(self):
        return self.code

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES


class OrderItem(models.Model):
    """قیمت و نام کالا در لحظه ثبت سفارش کپی می‌شود تا تغییرات بعدی فروشگاه سفارش را عوض نکند."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "shop.ShopProduct", null=True, on_delete=models.SET_NULL, related_name="order_items"
    )
    name = models.CharField("نام کالا", max_length=200)
    unit_display = models.CharField("واحد", max_length=30, blank=True)
    price = models.PositiveBigIntegerField("قیمت واحد (ریال)")
    list_price = models.PositiveBigIntegerField("قیمت مصرف‌کننده (ریال)", default=0)
    cost_price = models.PositiveBigIntegerField("قیمت تمام‌شده واحد در لحظه فروش (ریال)", default=0)
    bundle_name = models.CharField("بسته پیشنهادی", max_length=200, blank=True)
    quantity = models.PositiveSmallIntegerField("تعداد", default=1)

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"

    @property
    def line_total(self) -> int:
        return self.price * self.quantity


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=16, choices=Order.Status.choices)
    note = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
