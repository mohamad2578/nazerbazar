"""درگاه پرداخت اینترنتی.

هر پرداخت سفارش به درگاهِ «همان فروشگاه» می‌رود اگر فروشگاه درگاه اختصاصی فعال کرده باشد (پول مستقیم به حساب
خودش واریز می‌شود)؛ وگرنه درگاه پیش‌فرض سامانه (PAYMENT_BACKEND) استفاده می‌شود. شارژ کیف پول همیشه درگاه سامانه است.

درگاه‌ها:
  console  — شبیه‌ساز توسعه: بلافاصله «پرداخت موفق» حساب می‌شود (هیچ پولی جابه‌جا نمی‌شود)
  zarinpal — زرین‌پال (کد پذیرنده؛ در حالت آزمایشی از sandbox.zarinpal.com)
  zibal    — زیبال (کد پذیرنده؛ برای آزمایش کد «zibal»)

جریان: start() تراکنش را می‌سازد و نشانی هدایت کاربر به درگاه را برمی‌گرداند؛ درگاه کاربر را به callback
برمی‌گرداند و verify() پرداخت را تایید و اثرش را (تایید سفارش یا شارژ کیف پول) اعمال می‌کند.
"""
import json
import logging
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .commerce import Payment

log = logging.getLogger(__name__)


@dataclass
class Creds:
    provider: str          # console | zarinpal | zibal
    merchant: str = ""
    sandbox: bool = False
    own: bool = False      # درگاه اختصاصی فروشگاه (نه درگاه سامانه)


def _is_test_merchant(provider: str, merchant: str, sandbox: bool) -> bool:
    return bool(sandbox) or (provider == "zibal" and merchant.strip().lower() == "zibal")


def _creds(store=None) -> Creds:
    if store is not None:
        fin = getattr(store, "finance", None)
        if fin and fin.own_gateway:
            if _is_test_merchant(fin.gateway_provider, fin.gateway_merchant, fin.gateway_sandbox) and not settings.PAYMENT_ALLOW_MOCK and not settings.DEBUG:
                # کد آزمایشی/سندباکس درگاه همیشه «پرداخت موفق» می‌دهد؛ روی سرور واقعی نباید پذیرفته شود
                raise ValidationError({"payment_method": "درگاه این فروشگاه هنوز در حالت آزمایشی است؛ پرداخت اینترنتی فعلا ممکن نیست."})
            return Creds(fin.gateway_provider, fin.gateway_merchant, fin.gateway_sandbox, own=True)
    c = Creds(settings.PAYMENT_BACKEND, settings.ZARINPAL_MERCHANT_ID, settings.ZARINPAL_SANDBOX)
    if c.provider not in ("zarinpal", "zibal") and not settings.PAYMENT_ALLOW_MOCK:
        # بدون درگاه واقعی، «پرداخت موفق» قابل جعل است؛ پس پرداخت اینترنتی بسته می‌ماند
        raise ValidationError({"payment_method": "پرداخت اینترنتی هنوز فعال نشده است؛ روش دیگری انتخاب کنید یا بعدا تلاش کنید."})
    return c


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read() or b"{}")


def _zp_base(c: Creds) -> str:
    return "https://sandbox.zarinpal.com" if c.sandbox else "https://payment.zarinpal.com"


def _request(c: Creds, payment: Payment, user, callback_url: str, description: str) -> tuple[str, str]:
    """درخواست پرداخت به درگاه؛ (شناسه تراکنش، نشانی هدایت کاربر) را برمی‌گرداند."""
    if c.provider == "zarinpal":
        r = _post_json(f"{_zp_base(c)}/pg/v4/payment/request.json", {
            "merchant_id": c.merchant, "amount": payment.amount, "currency": "IRR", "callback_url": callback_url,
            "description": description or "پرداخت ناظر ۷۲۴", "metadata": {"mobile": user.mobile},
        })
        data = r.get("data") or {}
        if data.get("code") != 100 or not data.get("authority"):
            raise ValidationError({"payment_method": "درگاه پرداخت درخواست را نپذیرفت؛ کمی بعد دوباره تلاش کنید."})
        return data["authority"], f"{_zp_base(c)}/pg/StartPay/{data['authority']}"
    if c.provider == "zibal":
        r = _post_json("https://gateway.zibal.ir/v1/request", {
            "merchant": c.merchant, "amount": payment.amount, "callbackUrl": callback_url,
            "description": description or "پرداخت ناظر ۷۲۴", "mobile": user.mobile, "orderId": str(payment.pk),
        })
        if r.get("result") != 100 or not r.get("trackId"):
            raise ValidationError({"payment_method": "درگاه پرداخت درخواست را نپذیرفت؛ کمی بعد دوباره تلاش کنید."})
        return str(r["trackId"]), f"https://gateway.zibal.ir/start/{r['trackId']}"
    # شبیه‌ساز: بازگشت فوری موفق
    auth = f"MOCK{payment.pk}"
    sep = "&" if "?" in callback_url else "?"
    return auth, f"{callback_url}{sep}Authority={auth}&Status=OK"


def start(user, amount: int, purpose: str, callback_url: str, order=None, description: str = "", store=None) -> tuple[Payment, str]:
    """ثبت تراکنش و برگرداندن نشانی پرداخت. amount به ریال است؛ با store، درگاه اختصاصی فروشگاه (اگر فعال باشد) استفاده می‌شود."""
    if purpose == Payment.Purpose.WALLET:
        store = None
    c = _creds(store)
    payment = Payment.objects.create(
        user=user, purpose=purpose, order=order, amount=amount, gateway=c.provider, store=store if c.own else None,
        # اعتبار درگاه همان لحظه ثبت می‌شود تا تغییر تنظیمات فروشگاه وسط پرداخت، تایید را خراب نکند
        merchant=c.merchant if c.own else "", sandbox=c.sandbox if c.own else False,
    )
    try:
        payment.authority, url = _request(c, payment, user, callback_url, description)
    except ValidationError:
        payment.status, payment.detail = Payment.Status.FAILED, "رد درخواست"
        payment.save(update_fields=["status", "detail"])
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("%s request failed", c.provider)
        payment.status, payment.detail = Payment.Status.FAILED, f"{type(e).__name__}: {e}"[:300]
        payment.save(update_fields=["status", "detail"])
        raise ValidationError({"payment_method": "اتصال به درگاه پرداخت برقرار نشد؛ کمی بعد دوباره تلاش کنید."})
    payment.save(update_fields=["authority"])
    return payment, url


def _verify_remote(payment: Payment) -> tuple[bool, str, str]:
    """تایید پرداخت نزد درگاه؛ (موفق؟، شماره پیگیری، توضیح خطا) را برمی‌گرداند."""
    if payment.merchant:
        c = Creds(payment.gateway, payment.merchant, payment.sandbox, own=True)
    else:
        c = Creds(payment.gateway, settings.ZARINPAL_MERCHANT_ID, settings.ZARINPAL_SANDBOX)
    if payment.gateway not in ("zarinpal", "zibal") and not settings.PAYMENT_ALLOW_MOCK:
        return False, "", "شبیه‌ساز درگاه روی سرور واقعی غیرفعال است"
    if payment.gateway == "zarinpal":
        r = _post_json(f"{_zp_base(c)}/pg/v4/payment/verify.json", {
            "merchant_id": c.merchant, "amount": payment.amount, "authority": payment.authority,
        })
        data = r.get("data") or {}
        if data.get("code") in (100, 101):
            return True, str(data.get("ref_id", "")), ""
        return False, "", json.dumps(r, ensure_ascii=False)[:300]
    if payment.gateway == "zibal":
        r = _post_json("https://gateway.zibal.ir/v1/verify", {"merchant": c.merchant, "trackId": int(payment.authority)})
        # ۱۰۰ = تایید شد، ۲۰۱ = قبلا تایید شده بود
        if r.get("result") in (100, 201) and r.get("amount") in (None, payment.amount):
            return True, str(r.get("refNumber") or payment.authority), ""
        return False, "", json.dumps(r, ensure_ascii=False)[:300]
    return True, "MOCK", ""


@transaction.atomic
def verify(authority: str, ok: bool) -> Payment | None:
    """تایید پرداخت پس از بازگشت از درگاه؛ نتیجه idempotent است (بازگشت دوباره اثر دوباره ندارد)."""
    payment = Payment.objects.select_for_update().select_related("store__finance").filter(authority=authority).first()
    if not payment:
        return None
    if payment.status != Payment.Status.PENDING:
        return payment
    if not ok and payment.gateway not in ("zarinpal", "zibal"):
        payment.status, payment.detail = Payment.Status.FAILED, "پرداخت انجام نشد یا لغو شد"
        payment.save(update_fields=["status", "detail"])
        _on_failed(payment)
        return payment
    try:
        # حتی با «ناموفق» اعلام‌شده در آدرس بازگشت، نتیجه از خود درگاه پرسیده می‌شود (آدرس بازگشت قابل جعل است)
        paid, ref, err = _verify_remote(payment)
    except Exception as e:  # noqa: BLE001
        # نتیجه نامعلوم است؛ پرداخت در انتظار می‌ماند تا با تلاش دوباره تعیین تکلیف شود
        log.exception("%s verify failed", payment.gateway)
        payment.detail = f"{type(e).__name__}: {e}"[:300]
        payment.save(update_fields=["detail"])
        return payment
    if not paid:
        payment.status, payment.detail = Payment.Status.FAILED, err or "پرداخت انجام نشد یا لغو شد"
        payment.save(update_fields=["status", "detail"])
        _on_failed(payment)
        return payment
    payment.status, payment.ref_id, payment.paid_at = Payment.Status.PAID, ref, timezone.now()
    payment.save(update_fields=["status", "ref_id", "paid_at"])
    _on_paid(payment)
    return payment


def _on_paid(payment: Payment) -> None:
    from . import order_services, wallet
    from .commerce import WalletTx

    if payment.purpose == Payment.Purpose.WALLET:
        wallet.credit(payment.user, payment.amount, WalletTx.Kind.TOPUP, f"شارژ اینترنتی — پیگیری {payment.ref_id}")
    elif payment.order_id:
        order_services.mark_order_paid(payment.order, paid_amount=payment.amount)


def _on_failed(payment: Payment) -> None:
    from . import order_services

    if payment.order_id:
        order_services.release_unpaid_order(payment.order, "پرداخت ناموفق")
