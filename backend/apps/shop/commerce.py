"""بسته‌های پیشنهادی، کیف پول، پرداخت اینترنتی و نشانی‌های تحویل مشتری."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class ShopBundle(TimeStamped):
    """بسته پیشنهادی: چند کالای یک فروشگاه که با قیمت یکجا عرضه می‌شود (مثلا برنج + گوشت + مرغ)."""

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="bundles", verbose_name="فروشگاه")
    title = models.CharField("عنوان بسته", max_length=150)
    description = models.CharField("توضیح", max_length=300, blank=True)
    image = models.ImageField("تصویر", upload_to="bundles/", blank=True)
    price = models.PositiveBigIntegerField("قیمت بسته (ریال)")
    order = models.PositiveSmallIntegerField("الویت نمایش", default=0)
    is_active = models.BooleanField("نمایش", default=True, db_index=True)

    SCOPE = {"store": "store"}

    class Meta:
        verbose_name = "بسته پیشنهادی"
        verbose_name_plural = "بسته‌های پیشنهادی"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title


class ShopBundleItem(models.Model):
    bundle = models.ForeignKey(ShopBundle, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("shop.ShopProduct", on_delete=models.CASCADE, related_name="bundle_items")
    quantity = models.PositiveSmallIntegerField("تعداد", default=1)

    class Meta:
        unique_together = [("bundle", "product")]


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveBigIntegerField("موجودی (ریال)", default=0)

    class Meta:
        verbose_name = "کیف پول"
        verbose_name_plural = "کیف پول‌ها"


class WalletTx(models.Model):
    class Kind(models.TextChoices):
        TOPUP = "topup", "شارژ"
        ORDER = "order", "پرداخت سفارش"
        REFUND = "refund", "بازگشت وجه"
        ADMIN = "admin", "اعتبار هدیه/اصلاح مدیر"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="txs")
    amount = models.BigIntegerField("مبلغ (ریال؛ منفی = برداشت)")
    balance_after = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    note = models.CharField(max_length=200, blank=True)
    order = models.ForeignKey("shop.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Payment(models.Model):
    """یک تراکنش درگاه پرداخت اینترنتی (پرداخت سفارش یا شارژ کیف پول)."""

    class Purpose(models.TextChoices):
        ORDER = "order", "سفارش"
        WALLET = "wallet", "شارژ کیف پول"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        FAILED = "failed", "ناموفق"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    order = models.ForeignKey("shop.Order", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    amount = models.PositiveBigIntegerField("مبلغ (ریال)")
    gateway = models.CharField(max_length=20)
    authority = models.CharField(max_length=64, blank=True, db_index=True)
    ref_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class UserAddress(TimeStamped):
    """نشانی‌های ذخیره‌شده مشتری برای ارسال با پیک."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    title = models.CharField("عنوان", max_length=60, help_text="مثلا خانه، محل کار")
    address = models.CharField("نشانی", max_length=300)
    receiver_phone = models.CharField("تلفن تحویل‌گیرنده", max_length=15, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField("پیش‌فرض", default=False)

    class Meta:
        verbose_name = "نشانی مشتری"
        verbose_name_plural = "نشانی‌های مشتریان"
        ordering = ["-is_default", "-created_at"]
