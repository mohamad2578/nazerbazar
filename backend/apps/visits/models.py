from django.conf import settings
from django.db import models


class Visit(models.Model):
    """یک بازدید از سایت یا اپلیکیشن.

    برای حفظ حریم خصوصی، IP یا مشخصات دستگاه ذخیره نمی‌شود؛ بازدیدکننده فقط با یک شناسه
    تصادفی که مرورگر خودش می‌سازد (visitor) شناخته می‌شود تا «بازدیدکننده یکتا» شمرده شود.
    """

    class Kind(models.TextChoices):
        PAGE = "page", "بازدید صفحه"
        PRODUCT = "product", "بازدید کالا"

    class Platform(models.TextChoices):
        WEB = "web", "وب‌سایت"
        APP = "app", "اپلیکیشن اندروید"

    kind = models.CharField("نوع", max_length=10, choices=Kind.choices, default=Kind.PAGE)
    path = models.CharField("مسیر", max_length=300, blank=True)
    product = models.ForeignKey("market.Product", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="visits", verbose_name="کالا")
    visitor = models.CharField("شناسه بازدیدکننده", max_length=40, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+", verbose_name="کاربر")
    platform = models.CharField("بستر", max_length=5, choices=Platform.choices, default=Platform.WEB)
    created_at = models.DateTimeField("زمان", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "بازدید"
        verbose_name_plural = "بازدیدها"
        indexes = [
            models.Index(fields=["kind", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]
