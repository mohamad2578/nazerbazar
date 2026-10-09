from decimal import ROUND_CEILING, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStamped

# فروشگاه ممکن است عضو اتحادیه نباشد (زنجیره‌ای)؛ در آن حالت از مسیر اتحادیه‌های
# تحت پوشش در حوزه مسئولان دیده می‌شود.
STORE_CHAIN_SCOPE = {
    "province": ("store__union__chamber__county__province", "store__covered_unions__chamber__county__province"),
    "chamber": ("store__union__chamber", "store__covered_unions__chamber"),
    "union": ("store__union", "store__covered_unions"),
    "store": "store",
}


class Category(TimeStamped):
    name = models.CharField("عنوان", max_length=100, unique=True)
    icon = models.CharField("آیکن", max_length=40, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


def default_max_discount():
    return settings.MARKET["DEFAULT_MAX_DISCOUNT"]


class Unit(models.TextChoices):
    KG = "kg", "کیلوگرم"
    GRAM = "g", "گرم"
    PIECE = "piece", "عدد"
    PACK = "pack", "بسته"
    LITER = "l", "لیتر"
    CARTON = "carton", "کارتن"


class Product(TimeStamped):
    """کالایی که اتحادیه تعریف و نرخ‌گذاری می‌کند."""

    union = models.ForeignKey("orgs.Union", on_delete=models.PROTECT, related_name="products", verbose_name="اتحادیه")
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products", verbose_name="دسته"
    )
    commodity = models.ForeignKey(
        "observatory.Commodity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
        verbose_name="کالای اساسی مرتبط",
        help_text="برای رصد قیمت کالاهای اساسی و سبد خانوار",
    )
    name = models.CharField("نام کالا", max_length=200)
    unit = models.CharField("واحد", max_length=10, choices=Unit.choices, default=Unit.KG)
    unit_amount = models.DecimalField("مقدار واحد", max_digits=10, decimal_places=3, default=1)
    description = models.TextField("توضیحات", blank=True)
    image = models.ImageField("تصویر", upload_to="products/", blank=True)
    current_price = models.PositiveBigIntegerField("نرخ مصوب (ریال)", default=0)
    max_discount_percent = models.PositiveSmallIntegerField(
        "حداکثر تخفیف مجاز (%)", default=default_max_discount, validators=[MaxValueValidator(90)]
    )
    price_changed_at = models.DateTimeField("زمان آخرین تغییر نرخ", null=True, blank=True, db_index=True)
    is_active = models.BooleanField("فعال", default=True)

    SCOPE = {"province": "union__chamber__county__province", "chamber": "union__chamber", "union": "union"}

    class Meta:
        verbose_name = "کالا"
        verbose_name_plural = "کالاها"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def min_allowed_price(self) -> int:
        v = Decimal(self.current_price) * (Decimal(100 - self.max_discount_percent) / 100)
        return int(v.to_integral_value(ROUND_CEILING))


class OfficialPrice(models.Model):
    """نرخ مصوب هر کالا و تاریخچه آن.

    نرخی که **اتحادیه** ثبت می‌کند در وضعیت «در انتظار تایید» می‌ماند و تا تایید
    اتاق اصناف (یا اداره صمت/مدیر کل) روی سایت اعمال نمی‌شود. نرخی که **اداره صمت**،
    اتاق اصناف یا مدیر کل ثبت کند بی‌درنگ تایید‌شده محسوب و اعمال می‌شود.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تایید"
        APPROVED = "approved", "تاییدشده"
        REJECTED = "rejected", "رد شده"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_history")
    price = models.PositiveBigIntegerField("نرخ (ریال)", validators=[MinValueValidator(1)])
    previous_price = models.PositiveBigIntegerField(default=0)
    max_discount_percent = models.PositiveSmallIntegerField(default=20)
    note = models.CharField("توضیح", max_length=300, blank=True)
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.APPROVED, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField("زمان بررسی", null=True, blank=True)
    review_note = models.CharField("توضیح بررسی", max_length=300, blank=True)

    SCOPE = {"province": "product__union__chamber__county__province", "chamber": "product__union__chamber", "union": "product__union"}

    class Meta:
        verbose_name = "نرخ مصوب"
        verbose_name_plural = "تاریخچه نرخ‌های مصوب"
        ordering = ["-created_at"]


class StoreOffer(TimeStamped):
    """قیمت عرضه یک کالا در یک فروشگاه"""

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="offers", verbose_name="فروشگاه")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="offers", verbose_name="کالا")
    price = models.PositiveBigIntegerField("قیمت فروشگاه (ریال)")
    is_available = models.BooleanField("موجود", default=True)
    # زمانی که فروشگاه آخرین بار قیمت را ثبت/تایید کرده؛ مبنای قانون مهلت ۲۴ ساعته
    confirmed_at = models.DateTimeField("آخرین تایید قیمت", db_index=True)

    SCOPE = STORE_CHAIN_SCOPE

    class Meta:
        verbose_name = "قیمت فروشگاه"
        verbose_name_plural = "قیمت‌های فروشگاه‌ها"
        unique_together = [("store", "product")]
        indexes = [models.Index(fields=["product", "price"])]

    def __str__(self):
        return f"{self.store} / {self.product}: {self.price}"

    @property
    def is_stale(self) -> bool:
        p = self.product
        return bool(p.price_changed_at and self.confirmed_at < p.price_changed_at)

    @property
    def discount_percent(self):
        cp = self.product.current_price
        return round((cp - self.price) / cp * 100, 1) if cp else 0


class OfferLog(models.Model):
    offer = models.ForeignKey(StoreOffer, on_delete=models.CASCADE, related_name="logs")
    price = models.PositiveBigIntegerField()
    official_price = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Review(TimeStamped):
    """امتیاز و نظر شهروند درباره فروشگاه (اثبات اجتماعی)"""

    store = models.ForeignKey("orgs.Store", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField("امتیاز", validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField("نظر", max_length=500, blank=True)
    is_visible = models.BooleanField("نمایش", default=True)

    SCOPE = STORE_CHAIN_SCOPE

    class Meta:
        verbose_name = "نظر"
        verbose_name_plural = "نظرات"
        unique_together = [("store", "user")]
        ordering = ["-created_at"]


class DailySnapshot(models.Model):
    """عکس روزانه قیمت هر کالا در هر شهرستان — مبنای روندها، سبد خانوار و هشدارها"""

    date = models.DateField(db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="snapshots")
    county = models.ForeignKey("orgs.County", on_delete=models.CASCADE, related_name="snapshots")
    official_price = models.PositiveBigIntegerField()
    min_price = models.PositiveBigIntegerField(null=True)
    avg_price = models.PositiveBigIntegerField(null=True)
    max_price = models.PositiveBigIntegerField(null=True)
    offer_count = models.PositiveIntegerField(default=0)
    stale_count = models.PositiveIntegerField(default=0)

    SCOPE = {"province": "county__province", "chamber": "product__union__chamber", "union": "product__union"}

    class Meta:
        unique_together = [("date", "product", "county")]
        ordering = ["date"]
