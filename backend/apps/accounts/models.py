from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.utils import normalize_mobile


class Role(models.TextChoices):
    ADMIN = "admin", "مدیر کل سامانه"
    GOVERNORATE = "governorate", "استانداری"
    CHAMBER = "chamber", "اتاق اصناف"
    UNION = "union", "اتحادیه"
    STORE = "store", "فروشگاه"
    CITIZEN = "citizen", "شهروند"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, mobile, password=None, **extra):
        user = self.model(mobile=normalize_mobile(mobile), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=Role.ADMIN)
        return self.create_user(mobile, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    mobile = models.CharField("موبایل", max_length=11, unique=True)
    first_name = models.CharField("نام", max_length=80, blank=True)
    last_name = models.CharField("نام خانوادگی", max_length=80, blank=True)
    national_code = models.CharField("کد ملی", max_length=10, blank=True)
    role = models.CharField("نقش", max_length=20, choices=Role.choices, default=Role.CITIZEN, db_index=True)
    # حوزه دسترسی کاربران سازمانی (بسته به نقش یکی از این‌ها پر می‌شود)
    province = models.ForeignKey("orgs.Province", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    chamber = models.ForeignKey("orgs.Chamber", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    union = models.ForeignKey("orgs.Union", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    is_active = models.BooleanField("فعال", default=True)
    is_staff = models.BooleanField("دسترسی پنل جنگو", default=False)
    date_joined = models.DateTimeField("عضویت", default=timezone.now)

    SCOPE = {
        "province": ("province", "chamber__county__province", "union__chamber__county__province"),
        "chamber": ("chamber", "union__chamber"),
    }

    objects = UserManager()
    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return f"{self.full_name or self.mobile} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        self.mobile = normalize_mobile(self.mobile)


class OTP(models.Model):
    mobile = models.CharField(max_length=11, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    MAX_ATTEMPTS = 5

    class Meta:
        verbose_name = "کد یکبارمصرف"
        verbose_name_plural = "کدهای یکبارمصرف"

    @property
    def expired(self):
        return self.created_at + timedelta(seconds=settings.OTP_TTL_SECONDS) < timezone.now()


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "اعلان"
        verbose_name_plural = "اعلان‌ها"
        ordering = ["-created_at"]


def notify(users, title, body="", link=""):
    Notification.objects.bulk_create(
        [Notification(user=u, title=title, body=body, link=link) for u in users if u is not None]
    )
