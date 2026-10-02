"""ارسال پیامک؛ درایور از SMS_BACKEND انتخاب می‌شود تا در توسعه چیزی واقعا ارسال نشود."""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def send_otp(mobile: str, code: str) -> None:
    if settings.SMS_BACKEND == "kavenegar":
        params = urllib.parse.urlencode(
            {"receptor": mobile, "token": code, "template": settings.KAVENEGAR_OTP_TEMPLATE}
        )
        url = f"https://api.kavenegar.com/v1/{settings.KAVENEGAR_API_KEY}/verify/lookup.json?{params}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                json.loads(resp.read())
        except Exception:  # پیامک نباید درخواست کاربر را از کار بیندازد
            log.exception("kavenegar send failed for %s", mobile)
        return
    log.warning("OTP for %s: %s", mobile, code)
