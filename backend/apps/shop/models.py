"""فروشگاه اینترنتی فروشگاه‌ها.

این ماژول با «کالاهای اساسی» فرق دارد:
  • کالای اساسی را اتحادیه تعریف و نرخ مصوب می‌گذارد و فروشگاه فقط مجاز است
    برابر نرخ مصوب یا حداکثر ۲۰٪ کمتر قیمت بدهد (apps.market).
  • اینجا فروشگاه محصولات خودش را تعریف می‌کند و قیمت را خودش تعیین می‌کند؛
    هیچ سقف/کف نرخی اعمال نمی‌شود. یک ابزار تشویقی برای عضویت فروشندگان است.
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class ShopCategory(TimeStamped):
    """دسته‌بندی محصولات فروشگاه‌های اینترنتی (مشترک بین همه فروشگاه‌ها)."""

    name = models.CharField("عنوان", max_length=100, unique=True)
    icon = models.CharField("آیکن", max_length=40, blank=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "دسته محصولات فروشگاهی"
        verbose_name_plural = "دسته‌های محصولات فروشگاهی"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ShopProduct(TimeStamped):
    """محصول اختصاصی یک فروشگاه (کالای غیراساسی)؛ قیمت آزاد است اما پیش از نمایش
    عمومی باید کارشناس اداره صمت آن را تایید کند."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تایید صمت"
        APPROVED = "approved", "تاییدشده"
        REJECTED = "rejected", "رد شده"

    class Unit(models.TextChoices):
        PIECE = "piece", "عدد"
        KG = "kg", "کیلوگرم"
        GRAM = "g", "گرم"
        PACK = "pack", "بسته"
        LITER = "l", "لیتر"
        METER = "m", "متر"
        SERVICE = "service", "خدمت"

    store = models.ForeignKey(
        "orgs.Store", on_delete=models.CASCADE, related_name="shop_products", verbose_name="فروشگاه"
    )
    category = models.ForeignKey(
        ShopCategory, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="products", verbose_name="دسته",
    )
    name = models.CharField("نام محصول", max_length=200)
    description = models.TextField("توضیحات", blank=True)
    image = models.ImageField("تصویر", upload_to="shop/%Y/%m/", blank=True)
    price = models.PositiveBigIntegerField("قیمت (ریال)")
    old_price = models.PositiveBigIntegerField(
        "قیمت پیش از تخفیف (ریال)", null=True, blank=True,
        help_text="در صورت تکمیل، به‌صورت خط‌خورده و با درصد تخفیف نمایش داده می‌شود",
    )
    unit = models.CharField("واحد", max_length=10, choices=Unit.choices, default=Unit.PIECE)
    brand = models.CharField("برند/تولیدکننده", max_length=120, blank=True)
    is_available = models.BooleanField("موجود", default=True, db_index=True)
    is_active = models.BooleanField("نمایش در فروشگاه", default=True, db_index=True)
    order = models.PositiveSmallIntegerField("ترتیب نمایش", default=0)

    status = models.CharField("وضعیت تایید", max_length=10, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+", verbose_name="بررسی‌کننده")
    reviewed_at = models.DateTimeField("زمان بررسی", null=True, blank=True)
    review_note = models.CharField("توضیح بررسی", max_length=300, blank=True)

    SCOPE = {
        "province": ("store__union__chamber__county__province", "store__covered_unions__chamber__county__province"),
        "chamber": ("store__union__chamber", "store__covered_unions__chamber"),
        "union": ("store__union", "store__covered_unions"),
        "store": "store",
    }

    class Meta:
        verbose_name = "محصول فروشگاه"
        verbose_name_plural = "محصولات فروشگاه‌ها"
        ordering = ["order", "-created_at"]
        indexes = [models.Index(fields=["store", "is_active", "is_available", "status"])]

    def __str__(self):
        return f"{self.name} ({self.store.name})"

    @property
    def is_public(self) -> bool:
        """فقط محصول تاییدشده و فعال به مردم نمایش داده می‌شود."""
        return self.status == self.Status.APPROVED and self.is_active

    @property
    def discount_percent(self):
        if not self.old_price or self.old_price <= self.price:
            return None
        return round((self.old_price - self.price) / self.old_price * 100)


from .orders import Order, OrderEvent, OrderItem  # noqa: E402,F401  (ثبت مدل‌ها در اپ)
