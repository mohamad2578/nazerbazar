from django.db import models

from apps.core.models import TimeStamped


class Supplier(TimeStamped):
    """تامین‌کننده‌ای که از صفحه عمومی فرم ثبت‌نام را پر کرده است."""

    first_name = models.CharField("نام", max_length=60)
    last_name = models.CharField("نام خانوادگی", max_length=60)
    mobile = models.CharField("شماره تماس", max_length=11, db_index=True)
    product_type = models.CharField("نوع کالای قابل تامین", max_length=200)
    is_reviewed = models.BooleanField("بررسی شده", default=False)

    class Meta:
        verbose_name = "تامین‌کننده"
        verbose_name_plural = "تامین‌کنندگان"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
