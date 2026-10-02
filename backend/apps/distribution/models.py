"""توزیع کالاهای اساسی/یارانه‌ای و رهگیری محموله (ماژول TraceFood و سهمیه‌بندی هوشمند).

زنجیره: تخصیص استانی (Allocation) -> سهم اتحادیه (AllocationShare) -> سهمیه فروشگاه (Quota)
هر سهمیه کد رهگیری یکتا دارد و مراحل ارسال، تحویل و فروش آن ثبت می‌شود تا نشتی و
انحراف کالا و فاصله قیمت تخصیص تا مصرف‌کننده قابل سنجش باشد.
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class Allocation(TimeStamped):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "در حال توزیع"
        CLOSED = "closed", "بسته شده"

    province = models.ForeignKey("orgs.Province", on_delete=models.PROTECT, related_name="allocations", verbose_name="استان")
    commodity = models.ForeignKey(
        "observatory.Commodity", on_delete=models.PROTECT, related_name="allocations", verbose_name="کالا"
    )
    title = models.CharField("عنوان", max_length=200)
    supplier = models.CharField("تامین‌کننده/واردکننده", max_length=200, blank=True)
    total_quantity = models.DecimalField("مقدار کل", max_digits=14, decimal_places=2)
    unit = models.CharField("واحد", max_length=20, default="کیلوگرم")
    allocation_price = models.PositiveBigIntegerField("قیمت تخصیص (ریال/واحد)")
    consumer_price = models.PositiveBigIntegerField("سقف قیمت مصرف‌کننده (ریال/واحد)")
    starts_on = models.DateField("شروع توزیع")
    ends_on = models.DateField("پایان توزیع", null=True, blank=True)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField("توضیحات", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    SCOPE = {
        "province": "province",
        "chamber": "shares__union__chamber",
        "union": "shares__union",
        "store": "shares__quotas__store",
    }

    class Meta:
        verbose_name = "تخصیص"
        verbose_name_plural = "تخصیص‌ها"
        ordering = ["-starts_on", "-pk"]

    def __str__(self):
        return self.title


class AllocationShare(TimeStamped):
    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name="shares")
    union = models.ForeignKey("orgs.Union", on_delete=models.PROTECT, related_name="allocation_shares", verbose_name="اتحادیه")
    quantity = models.DecimalField("مقدار", max_digits=14, decimal_places=2)

    SCOPE = {"province": "allocation__province", "chamber": "union__chamber", "union": "union"}

    class Meta:
        unique_together = [("allocation", "union")]
        verbose_name = "سهم اتحادیه"
        verbose_name_plural = "سهم اتحادیه‌ها"


class Quota(TimeStamped):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "تخصیص داده شد"
        DISPATCHED = "dispatched", "ارسال شد"
        RECEIVED = "received", "تحویل فروشگاه"
        SOLD_OUT = "sold_out", "فروش کامل"
        CANCELED = "canceled", "لغو"

    share = models.ForeignKey(AllocationShare, on_delete=models.CASCADE, related_name="quotas")
    store = models.ForeignKey("orgs.Store", on_delete=models.PROTECT, related_name="quotas", verbose_name="فروشگاه")
    tracking_code = models.CharField("کد رهگیری", max_length=12, unique=True)
    quantity = models.DecimalField("مقدار سهمیه", max_digits=14, decimal_places=2)
    received_quantity = models.DecimalField("مقدار تحویل‌شده", max_digits=14, decimal_places=2, null=True, blank=True)
    sold_quantity = models.DecimalField("مقدار فروخته‌شده", max_digits=14, decimal_places=2, default=0)
    carrier = models.CharField("حمل‌کننده/توزیع‌کننده", max_length=150, blank=True)
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.ASSIGNED, db_index=True)

    SCOPE = {
        "province": "share__allocation__province",
        "chamber": "share__union__chamber",
        "union": "share__union",
        "store": "store",
    }

    class Meta:
        verbose_name = "سهمیه فروشگاه"
        verbose_name_plural = "سهمیه فروشگاه‌ها"
        ordering = ["-created_at"]

    @property
    def remaining(self):
        return float(self.received_quantity or 0) - float(self.sold_quantity or 0)


class QuotaEvent(models.Model):
    quota = models.ForeignKey(Quota, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=12, choices=Quota.Status.choices)
    note = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
