"""رصدخانه قیمت و تامین کالاهای اساسی (ماژول MarketSight پیشنهاد «هر خرید یک مناقصه»).

- Commodity: فهرست کالاهای اساسی (۲۴ قلم مصرفی + نهاده‌های دامی) و سهم هر کدام در سبد ماهانه خانوار
- CommodityReport: جدول‌های الف و ب هر کالا (نیاز، تولید، واردات، بهای تمام‌شده، قیمت در زنجیره از
  مزرعه/کشتارگاه تا مصرف‌کننده، مقایسه با کشور همسایه) برای هر استان یا کل کشور در هر دوره
- Alert: هشدار خودکار جهش قیمت، کمبود عرضه، ترک مهلت به‌روزرسانی و افزایش شکایات
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class Commodity(TimeStamped):
    class Group(models.TextChoices):
        PROTEIN = "protein", "پروتئینی"
        DAIRY = "dairy", "لبنیات"
        GRAIN = "grain", "غلات و حبوبات"
        OIL_SUGAR = "oil_sugar", "روغن، قند و شکر"
        PRODUCE = "produce", "صیفی و تره‌بار"
        HYGIENE = "hygiene", "بهداشتی و شوینده"
        FEED = "feed", "نهاده دامی"
        OTHER = "other", "سایر"

    name = models.CharField("نام کالا", max_length=120, unique=True)
    group = models.CharField("گروه", max_length=12, choices=Group.choices, default=Group.OTHER)
    unit = models.CharField("واحد", max_length=20, default="کیلوگرم")
    subsidized = models.BooleanField("وارداتی با ارز دولتی/یارانه‌ای", default=False)
    basket_monthly_qty = models.DecimalField(
        "مقدار ماهانه در سبد خانوار", max_digits=8, decimal_places=2, default=0,
        help_text="صفر یعنی در سبد خانوار محاسبه نمی‌شود",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "کالای اساسی"
        verbose_name_plural = "کالاهای اساسی"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class CommodityReport(TimeStamped):
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="reports")
    province = models.ForeignKey(
        "orgs.Province", null=True, blank=True, on_delete=models.CASCADE, related_name="commodity_reports",
        help_text="خالی = گزارش ملی",
    )
    period = models.DateField("تاریخ دوره", db_index=True)
    # ─── جدول الف: وضعیت نیاز و تامین ───
    annual_need_kt = models.DecimalField("نیاز سالانه (هزار تن)", max_digits=12, decimal_places=2, null=True, blank=True)
    annual_production_kt = models.DecimalField("تولید سالانه (هزار تن)", max_digits=12, decimal_places=2, null=True, blank=True)
    imports_kt = models.DecimalField("واردات (هزار تن)", max_digits=12, decimal_places=2, null=True, blank=True)
    import_price = models.PositiveBigIntegerField("قیمت واردات (ریال/کیلو)", null=True, blank=True)
    clearance_cost = models.PositiveBigIntegerField("هزینه ترخیص و حمل (ریال/کیلو)", null=True, blank=True)
    neighbor_price_usd = models.DecimalField("قیمت در کشور همسایه (دلار/کیلو)", max_digits=8, decimal_places=2, null=True, blank=True)
    neighbor_country = models.CharField("کشور همسایه", max_length=40, default="عراق", blank=True)
    per_capita_stat = models.DecimalField("سرانه مصرف طبق آمار (کیلو)", max_digits=8, decimal_places=2, null=True, blank=True)
    # ─── جدول ب: قیمت در زنجیره (ریال) ───
    producer_price = models.PositiveBigIntegerField("قیمت تولیدکننده/سر مزرعه/زنده", null=True, blank=True)
    wholesale_price = models.PositiveBigIntegerField("قیمت عمده/کشتارگاه", null=True, blank=True)
    consumer_price_county = models.PositiveBigIntegerField("قیمت مصرف‌کننده در شهرستان", null=True, blank=True)
    consumer_price_center = models.PositiveBigIntegerField("قیمت مصرف‌کننده در مرکز استان", null=True, blank=True)
    consumer_price_tehran = models.PositiveBigIntegerField("قیمت مصرف‌کننده در تهران", null=True, blank=True)
    national_min = models.PositiveBigIntegerField("ارزان‌ترین قیمت استان‌ها", null=True, blank=True)
    national_max = models.PositiveBigIntegerField("گران‌ترین قیمت استان‌ها", null=True, blank=True)
    national_avg = models.PositiveBigIntegerField("متوسط قیمت کشور", null=True, blank=True)
    source = models.CharField("منبع", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    SCOPE = {"province": "province"}

    class Meta:
        verbose_name = "گزارش تامین و قیمت"
        verbose_name_plural = "گزارش‌های تامین و قیمت"
        ordering = ["-period", "commodity__order"]
        unique_together = [("commodity", "province", "period")]

    @property
    def landed_cost(self):
        if self.import_price is None:
            return None
        return self.import_price + (self.clearance_cost or 0)

    @property
    def per_capita_supply(self):
        """سرانه تامین = (تولید + واردات) / جمعیت کشور (میلیون نفر)"""
        if self.annual_production_kt is None:
            return None
        total_kt = float(self.annual_production_kt) + float(self.imports_kt or 0)
        return round(total_kt / settings_population_million(), 2)

    @property
    def supply_gap_kt(self):
        if self.annual_need_kt is None or self.annual_production_kt is None:
            return None
        return float(self.annual_need_kt) - float(self.annual_production_kt) - float(self.imports_kt or 0)

    @property
    def chain_markup_percent(self):
        """فاصله قیمت تولید تا مصرف (درصد) — شاخص اثر واسطه‌ها"""
        base = self.wholesale_price or self.producer_price
        final = self.national_avg or self.consumer_price_center or self.consumer_price_county
        if not base or not final:
            return None
        return round((final - base) / base * 100, 1)


def settings_population_million():
    return float(getattr(settings, "COUNTRY_POPULATION_MILLION", 86))


class Alert(models.Model):
    class Kind(models.TextChoices):
        OFFICIAL_JUMP = "official_jump", "جهش نرخ مصوب"
        MARKET_JUMP = "market_jump", "جهش قیمت بازار"
        SHORTAGE = "shortage", "کاهش عرضه"
        STALE = "stale", "عدم به‌روزرسانی قیمت"
        COMPLAINTS = "complaints", "افزایش شکایات"

    class Level(models.TextChoices):
        INFO = "info", "اطلاع"
        WARNING = "warning", "هشدار"
        CRITICAL = "critical", "بحرانی"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.WARNING)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    product = models.ForeignKey("market.Product", null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    store = models.ForeignKey("orgs.Store", null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    county = models.ForeignKey("orgs.County", null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    change_percent = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    dedupe_key = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    SCOPE = {"province": "county__province", "chamber": "county__chambers", "union": "product__union"}

    class Meta:
        verbose_name = "هشدار"
        verbose_name_plural = "هشدارها"
        ordering = ["-created_at"]
