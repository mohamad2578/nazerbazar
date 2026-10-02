from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStamped


class Province(TimeStamped):
    name = models.CharField("نام استان", max_length=80, unique=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    SCOPE = {"province": "pk"}

    class Meta:
        verbose_name = "استان"
        verbose_name_plural = "استان‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class County(TimeStamped):
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="counties", verbose_name="استان")
    name = models.CharField("نام شهرستان", max_length=80)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    population = models.PositiveIntegerField("جمعیت", null=True, blank=True)

    SCOPE = {"province": "province", "chamber": "chambers"}

    class Meta:
        verbose_name = "شهرستان"
        verbose_name_plural = "شهرستان‌ها"
        ordering = ["province__name", "name"]
        unique_together = [("province", "name")]

    def __str__(self):
        return self.name


class Chamber(TimeStamped):
    """اتاق اصناف شهرستان"""

    county = models.ForeignKey(County, on_delete=models.PROTECT, related_name="chambers", verbose_name="شهرستان")
    name = models.CharField("عنوان", max_length=150)
    address = models.CharField("نشانی", max_length=300, blank=True)
    phone = models.CharField("تلفن", max_length=20, blank=True)

    SCOPE = {"province": "county__province", "chamber": "pk"}

    class Meta:
        verbose_name = "اتاق اصناف"
        verbose_name_plural = "اتاق‌های اصناف"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Union(TimeStamped):
    """اتحادیه صنفی (خواربار، قصابان، میوه و تره‌بار و ...)"""

    chamber = models.ForeignKey(Chamber, on_delete=models.PROTECT, related_name="unions", verbose_name="اتاق اصناف")
    name = models.CharField("عنوان", max_length=150)
    guild = models.CharField("رسته صنفی", max_length=100, blank=True)
    logo = models.ImageField("لوگو", upload_to="unions/", blank=True)
    address = models.CharField("نشانی", max_length=300, blank=True)
    phone = models.CharField("تلفن", max_length=20, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    SCOPE = {"province": "chamber__county__province", "chamber": "chamber", "union": "pk"}

    class Meta:
        verbose_name = "اتحادیه"
        verbose_name_plural = "اتحادیه‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def county(self):
        return self.chamber.county


class Store(TimeStamped):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تایید"
        ACTIVE = "active", "فعال"
        REJECTED = "rejected", "رد شده"
        SUSPENDED = "suspended", "تعلیق"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stores", verbose_name="مالک")
    union = models.ForeignKey(Union, on_delete=models.PROTECT, related_name="stores", verbose_name="اتحادیه")
    name = models.CharField("نام فروشگاه", max_length=150)
    license_no = models.CharField("شماره پروانه کسب", max_length=50, blank=True)
    phone = models.CharField("تلفن", max_length=20, blank=True)
    address = models.CharField("نشانی", max_length=300)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    working_hours = models.CharField("ساعات کاری", max_length=100, blank=True)
    photo = models.ImageField("تصویر", upload_to="stores/", blank=True)
    license_image = models.ImageField("تصویر پروانه", upload_to="stores/licenses/", blank=True)
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    status_reason = models.TextField("دلیل رد/تعلیق", blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_verified = models.BooleanField("نشان اعتماد", default=False, help_text="احراز هویت کامل توسط اتحادیه")
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    SCOPE = {
        "province": "union__chamber__county__province",
        "chamber": "union__chamber",
        "union": "union",
        "store": "self",
    }

    class Meta:
        verbose_name = "فروشگاه"
        verbose_name_plural = "فروشگاه‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def set_status(self, status, by, reason=""):
        self.status = status
        self.status_reason = reason
        self.reviewed_at = timezone.now()
        self.reviewed_by = by
        self.save(update_fields=["status", "status_reason", "reviewed_at", "reviewed_by", "updated_at"])
