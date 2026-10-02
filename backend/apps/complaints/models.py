from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class Complaint(TimeStamped):
    class Kind(models.TextChoices):
        OVERPRICE = "overprice", "گران‌فروشی"
        NOT_HONORED = "not_honored", "عدم رعایت قیمت اعلام‌شده"
        UNAVAILABLE = "unavailable", "عدم عرضه با وجود اعلام موجودی"
        QUALITY = "quality", "کیفیت نامناسب"
        WEIGHT = "weight", "کم‌فروشی"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        NEW = "new", "ثبت شده"
        REVIEWING = "reviewing", "در حال بررسی"
        INSPECTION = "inspection", "ارجاع به بازرسی"
        RESOLVED = "resolved", "رسیدگی شد"
        REJECTED = "rejected", "رد شد"

    tracking_code = models.CharField("کد رهگیری", max_length=12, unique=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="complaints")
    reporter_name = models.CharField("نام گزارش‌دهنده", max_length=120)
    kind = models.CharField("نوع تخلف", max_length=20, choices=Kind.choices, default=Kind.OVERPRICE)
    store = models.ForeignKey("orgs.Store", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints")
    product = models.ForeignKey("market.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    # مسیر ارجاع: اتحادیه مسئول رسیدگی، اتاق اصناف رونوشت
    union = models.ForeignKey("orgs.Union", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints")
    chamber = models.ForeignKey("orgs.Chamber", on_delete=models.PROTECT, related_name="complaints")
    # فروشنده ثبت‌نشده در سامانه
    shop_name = models.CharField("نام فروشگاه", max_length=150, blank=True)
    shop_address = models.CharField("نشانی فروشگاه", max_length=300, blank=True)
    # اطلاعات لحظه ثبت (برای استناد)
    announced_price = models.PositiveBigIntegerField("قیمت اعلامی فروشگاه", null=True, blank=True)
    official_price = models.PositiveBigIntegerField("نرخ مصوب", null=True, blank=True)
    paid_price = models.PositiveBigIntegerField("قیمت دریافتی", null=True, blank=True)
    description = models.TextField("شرح")
    attachment = models.FileField("تصویر فاکتور/مستند", upload_to="complaints/%Y/%m/", blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    violation_confirmed = models.BooleanField("تخلف محرز شد", null=True, blank=True)
    resolution = models.TextField("نتیجه رسیدگی", blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    chamber_seen_at = models.DateTimeField(null=True, blank=True)

    SCOPE = {"province": "chamber__county__province", "chamber": "chamber", "union": "union", "store": "store"}

    class Meta:
        verbose_name = "شکایت"
        verbose_name_plural = "شکایات"
        ordering = ["-created_at"]

    def __str__(self):
        return self.tracking_code


class ComplaintEvent(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=Complaint.Status.choices, blank=True)
    note = models.TextField(blank=True)
    is_public = models.BooleanField("قابل مشاهده برای شهروند", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
