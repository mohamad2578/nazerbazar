from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.sms import send_otp
from apps.core.utils import normalize_mobile, random_code, to_en_digits

from .models import OTP, User


def request_otp(mobile: str) -> OTP:
    mobile = normalize_mobile(mobile)
    last = OTP.objects.filter(mobile=mobile, used=False).order_by("-created_at").first()
    if last and not last.expired and (timezone.now() - last.created_at).total_seconds() < 60:
        raise ValidationError({"mobile": "کد قبلی هنوز معتبر است؛ یک دقیقه دیگر تلاش کنید."})
    otp = OTP.objects.create(mobile=mobile, code=random_code(5))
    send_otp(mobile, otp.code)
    return otp


@transaction.atomic
def verify_otp(mobile: str, code: str) -> User:
    mobile = normalize_mobile(mobile)
    otp = OTP.objects.select_for_update().filter(mobile=mobile, used=False).order_by("-created_at").first()
    if not otp or otp.expired or otp.attempts >= OTP.MAX_ATTEMPTS:
        raise ValidationError({"code": "کد منقضی شده است؛ دوباره درخواست دهید."})
    if otp.code != to_en_digits(code).strip():
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise ValidationError({"code": "کد وارد شده صحیح نیست."})
    otp.used = True
    otp.save(update_fields=["used"])
    user, _ = User.objects.get_or_create(mobile=mobile)
    if not user.is_active:
        raise ValidationError({"mobile": "حساب کاربری غیرفعال است."})
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return user


def otp_debug_payload(otp: OTP) -> dict:
    return {"debug_code": otp.code} if settings.OTP_ECHO else {}
