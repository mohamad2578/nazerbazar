"""ارسال پیامک؛ درایور از SMS_BACKEND انتخاب می‌شود تا در توسعه چیزی واقعا ارسال نشود.

درایورها: console (فقط لاگ)، ghasedak (ghasedak.me)، kavenegar.
ارسال هرگز درخواست کاربر را از کار نمی‌اندازد: خطا لاگ می‌شود و هر پیامک (موفق یا ناموفق)
در جدول SmsLog ثبت می‌شود تا مدیر بتواند ببیند چه چیزی به چه کسی رفته است.
"""
import json
import logging
import threading
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

GHASEDAK_BASE = "https://api.ghasedak.me/v2"

PRICE_CHANGE_TEXT = (
    "فروشگاه گرامی {store}\n"
    "حداکثر قیمت {product} به {price} تومان تغییر یافت. خواهشمند است حداکثر ظرف مدت ۲۴ ساعت نسبت به "
    "اعلام قیمت جدید اقدام فرمایید؛ در غیر این صورت قیمت اعلامی قبلی باقی می‌ماند و مسئولیت آن بر عهده "
    "فروشگاه خواهد بود.\n"
    "ناظر ۷۲۴"
)


def _post(url: str, data: dict, headers: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", **headers})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def _ghasedak_text(mobile: str, text: str) -> dict:
    data = {"message": text, "receptor": mobile}
    if settings.GHASEDAK_LINE:
        data["linenumber"] = settings.GHASEDAK_LINE
    return _post(f"{GHASEDAK_BASE}/sms/send/simple", data, {"apikey": settings.GHASEDAK_API_KEY})


def _ghasedak_template(mobile: str, template: str, *params: str) -> dict:
    """ارسال با قالب تاییدشده (verification): پارامترها جایگزین %param1% و … در متن قالب می‌شوند."""
    data = {"receptor": mobile, "type": "1", "template": template}
    for i, v in enumerate(params, 1):
        data[f"param{i}"] = " ".join(str(v).split())[:60]    # قاصدک خط جدید و متن بلند در پارامتر را رد می‌کند
    return _post(f"{GHASEDAK_BASE}/verification/send/simple", data, {"apikey": settings.GHASEDAK_API_KEY})


def _record(kind: str, mobile: str, text: str, ok: bool, detail: str) -> None:
    try:
        from .models import SmsLog

        SmsLog.objects.create(kind=kind, mobile=mobile, text=text[:500], ok=ok, detail=detail[:300])
    except Exception:  # ثبت لاگ نباید چیزی را خراب کند
        log.exception("sms log failed")


def send_text(mobile: str, text: str, kind: str = "other") -> bool:
    """ارسال یک پیامک متنی با درایور فعال؛ True یعنی سرویس‌دهنده پیام را پذیرفته است."""
    backend = settings.SMS_BACKEND
    try:
        if backend == "ghasedak":
            r = _ghasedak_text(mobile, text)
            ok = (r.get("result") or {}).get("code") == 200
            _record(kind, mobile, text, ok, json.dumps(r, ensure_ascii=False))
            return ok
        if backend == "kavenegar":
            params = urllib.parse.urlencode({"receptor": mobile, "message": text})
            url = f"https://api.kavenegar.com/v1/{settings.KAVENEGAR_API_KEY}/sms/send.json?{params}"
            with urllib.request.urlopen(url, timeout=15) as resp:
                r = json.loads(resp.read())
            ok = (r.get("return") or {}).get("status") == 200
            _record(kind, mobile, text, ok, json.dumps(r, ensure_ascii=False))
            return ok
    except Exception as e:  # noqa: BLE001
        log.exception("sms send failed for %s", mobile)
        _record(kind, mobile, text, False, f"{type(e).__name__}: {e}")
        return False
    log.warning("SMS to %s: %s", mobile, text)
    _record(kind, mobile, text, True, "console")
    return True


def send_price_change(mobile: str, store: str, product: str, price_text: str) -> bool:
    """پیامک تغییر قیمت؛ با قالب قاصدک (GHASEDAK_PRICE_TEMPLATE) و در نبودش با متن آزاد."""
    text = PRICE_CHANGE_TEXT.format(store=store, product=product, price=price_text)
    template = settings.GHASEDAK_PRICE_TEMPLATE
    if settings.SMS_BACKEND == "ghasedak" and template:
        try:
            r = _ghasedak_template(mobile, template, store, product, price_text)
            ok = (r.get("result") or {}).get("code") == 200
            _record("price_change", mobile, text, ok, json.dumps(r, ensure_ascii=False))
            return ok
        except Exception as e:  # noqa: BLE001
            log.exception("ghasedak price template failed for %s", mobile)
            _record("price_change", mobile, text, False, f"{type(e).__name__}: {e}")
            return False
    return send_text(mobile, text, "price_change")


def send_price_change_sms(mobile: str, store: str, product: str, price_toman: int) -> None:
    """پیامک تغییر حداکثر قیمت به فروشگاه؛ در رشته جدا ارسال می‌شود تا ثبت قیمت کند نشود."""
    from django.db import transaction

    price = f"{price_toman:,}"
    # بعد از ثبت قطعی قیمت در دیتابیس و در رشته جدا؛ اگر ثبت قیمت برگردد، پیامکی نمی‌رود
    transaction.on_commit(lambda: threading.Thread(target=send_price_change, args=(mobile, store, product, price), daemon=True).start())


def send_otp(mobile: str, code: str) -> None:
    if settings.SMS_BACKEND == "ghasedak":
        try:
            if settings.GHASEDAK_OTP_TEMPLATE:
                r = _post(f"{GHASEDAK_BASE}/verification/send/simple",
                          {"receptor": mobile, "type": "1", "template": settings.GHASEDAK_OTP_TEMPLATE, "param1": code},
                          {"apikey": settings.GHASEDAK_API_KEY})
                _record("otp", mobile, "کد تایید", (r.get("result") or {}).get("code") == 200,
                        json.dumps(r, ensure_ascii=False))
            else:
                send_text(mobile, f"کد ورود به ناظر ۷۲۴: {code}", "otp")
        except Exception as e:  # noqa: BLE001
            log.exception("ghasedak otp failed for %s", mobile)
            _record("otp", mobile, "کد تایید", False, f"{type(e).__name__}: {e}")
        return
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
