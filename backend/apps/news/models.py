from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStamped


class NewsItem(TimeStamped):
    """خبر یا اطلاعیه‌ای که اداره صمت و مدیر کل منتشر می‌کنند."""

    title = models.CharField("عنوان خبر", max_length=200)
    image = models.ImageField("عکس خبر", upload_to="news/", blank=True)
    body = models.TextField("متن خبر")
    is_published = models.BooleanField("منتشر شود", default=True, db_index=True)
    published_at = models.DateTimeField("زمان انتشار", default=timezone.now, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+", verbose_name="ثبت‌کننده")

    class Meta:
        verbose_name = "خبر"
        verbose_name_plural = "اخبار"
        ordering = ["-published_at"]

    def __str__(self):
        return self.title
