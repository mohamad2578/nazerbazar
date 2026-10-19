from django.db import models


class TimeStamped(models.Model):
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("به‌روزرسانی", auto_now=True)

    class Meta:
        abstract = True


# بخش‌هایی از پنل که مدیر کل می‌تواند برای اتحادیه‌ها روشن یا خاموش کند (کلید ← عنوان)
UNION_SECTIONS = {
    "stores": "کارتابل فروشگاه‌ها",
    "products": "حداکثر قیمت کالاهای اساسی",
    "other_prices": "حداکثر قیمت سایر کالاها",
    "orders": "سفارش‌ها",
    "complaints": "شکایات",
    "quotas": "سهمیه‌ها، تخصیص و توزیع",
    "alerts": "هشدارها",
    "reports": "گزارش‌های تحلیلی",
    "observatory": "رصدخانه کالای اساسی",
}


# بخش‌های گزارش که مدیر کل می‌تواند برای کاربران اداره صمت روشن یا خاموش کند
SAMT_REPORTS = {
    "prices": "روند قیمت و تغییرات حداکثر قیمت",
    "complaints": "گزارش شکایات",
    "unions": "عملکرد اتحادیه‌ها",
    "counties": "وضعیت شهرستان‌ها",
    "basket": "سبد خانوار",
    "distribution": "تخصیص و توزیع",
    "visits": "آمار بازدید سامانه",
}


def _all_union_sections():
    return list(UNION_SECTIONS)


def _all_samt_reports():
    return list(SAMT_REPORTS)


class SystemSettings(models.Model):
    """تنظیمات سراسری سامانه که مدیر کل از پنل تعیین می‌کند (فقط یک ردیف)."""

    union_can_set_prices = models.BooleanField(
        "اتحادیه می‌تواند حداکثر قیمت ثبت یا تغییر دهد", default=True)
    snap_store_prices = models.BooleanField(
        "با تغییر حداکثر قیمت، قیمت همه فروشگاه‌ها برابر آن شود", default=True,
        help_text="خاموش: هر فروشگاه آخرین قیمت خودش را نگه می‌دارد، مگر اینکه خارج از بازه مجاز جدید باشد.")
    union_sections = models.JSONField("بخش‌های در دسترس اتحادیه", default=_all_union_sections)
    samt_reports = models.JSONField("گزارش‌های قابل مشاهده برای اداره صمت", default=_all_samt_reports)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        verbose_name = "تنظیمات سامانه"
        verbose_name_plural = "تنظیمات سامانه"

    @classmethod
    def get(cls) -> "SystemSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def union_allows(self, section: str) -> bool:
        return section in (self.union_sections or [])

    def samt_report_allowed(self, key: str) -> bool:
        return key in (self.samt_reports or [])


def require_report(user, key: str) -> None:
    """اگر مدیر کل این گزارش را برای اداره صمت بسته باشد، دسترسی رد می‌شود."""
    from rest_framework.exceptions import PermissionDenied

    role = getattr(user, "role", None)
    if role == "samt" and not SystemSettings.get().samt_report_allowed(key):
        raise PermissionDenied("مشاهده این گزارش برای اداره صمت توسط مدیر سامانه غیرفعال شده است.")
    # برای اتحادیه، کل بخش «گزارش‌های تحلیلی» یک کلید دارد (آمار بازدید اصلا برای اتحادیه نیست)
    if role == "union" and key != "visits" and not SystemSettings.get().union_allows("reports"):
        raise PermissionDenied("بخش گزارش‌ها برای اتحادیه‌ها غیرفعال است.")
