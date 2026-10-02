from django.db import models

from apps.core.models import TimeStamped


class Slide(TimeStamped):
    """اسلاید نمایشی صفحه اصلی سایت (بنر تبلیغاتی/اطلاع‌رسانی)."""

    title = models.CharField("عنوان", max_length=150)
    subtitle = models.CharField("زیرعنوان", max_length=300, blank=True)
    image = models.ImageField("تصویر", upload_to="slides/")
    link_url = models.CharField("لینک مقصد", max_length=300, blank=True, help_text="مثلا /p/12 یا یک آدرس خارجی")
    link_label = models.CharField("متن دکمه", max_length=50, blank=True, default="مشاهده")
    order = models.PositiveSmallIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "اسلاید"
        verbose_name_plural = "اسلایدهای صفحه اصلی"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title
