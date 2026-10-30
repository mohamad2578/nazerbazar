"""درگاه پرداخت اینترنتی.

PAYMENT_BACKEND:
  console  — شبیه‌ساز توسعه: بلافاصله «پرداخت موفق» حساب می‌شود (هیچ پولی جابه‌جا نمی‌شود)
  zarinpal — زرین‌پال (ZARINPAL_MERCHANT_ID؛ با ZARINPAL_SANDBOX=1 در محیط آزمایشی)

جریان: start() تراکنش را می‌سازد و نشانی هدایت کاربر به درگاه را برمی‌گرداند؛ درگاه کاربر را به
callback برمی‌گرداند و verify() پرداخت را تایید و اثرش را (تایید سفارش یا شارژ کیف پول) اعمال می‌کند.
"""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .commerce import Payment

log = logging.getLogger(__name__)


def _zarinpal_base() -> str:
    return "https://sandbox.zarinpal.com" if settings.ZARINPAL_SANDBOX else "https://payment.zarinpal.com"


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read() or b"{}")


def start(user, amount: int, purpose: str, callback_url: str, order=None, description: str = "") -> tuple[Payment, str]:
    """ثبت تراکنش و برگرداندن نشانی پرداخت. amount به ریال است."""
    backend = settings.PAYMENT_BACKEND
    payment = Payment.objects.create(user=user, purpose=purpose, order=order, amount=amount, gateway=backend)
    if backend == "zarinpal":
        try:
            r = _post_json(f"{_zarinpal_base()}/pg/v4/payment/request.json", {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID, "amount": amount, "currency": "IRR",
                "callback_url": callback_url, "description": description or "پرداخت ناظر ۷۲۴",
                "metadata": {"mobile": user.mobile},
            })
            data = r.get("data") or {}
            if data.get("code") != 100 or not data.get("authority"):
                raise ValidationError({"payment_method": "درگاه پرداخت درخواست را نپذیرفت؛ کمی بعد دوباره تلاش کنید."})
            payment.authority = data["authority"]
            payment.save(update_fields=["authority"])
            return payment, f"{_zarinpal_base()}/pg/StartPay/{payment.authority}"
        except ValidationError:
            payment.status, payment.detail = Payment.Status.FAILED, "رد درخواست"
            payment.save(update_fields=["status", "detail"])
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("zarinpal request failed")
            payment.status, payment.detail = Payment.Status.FAILED, f"{type(e).__name__}: {e}"[:300]
            payment.save(update_fields=["status", "detail"])
            raise ValidationError({"payment_method": "اتصال به درگاه پرداخت برقرار نشد؛ کمی بعد دوباره تلاش کنید."})
    # شبیه‌ساز: بازگشت فوری موفق
    payment.authority = f"MOCK{payment.pk}"
    payment.save(update_fields=["authority"])
    sep = "&" if "?" in callback_url else "?"
    return payment, f"{callback_url}{sep}Authority={payment.authority}&Status=OK"


@transaction.atomic
def verify(authority: str, ok: bool) -> Payment | None:
    """تایید پرداخت پس از بازگشت از درگاه؛ نتیجه idempotent است (بازگشت دوباره اثر دوباره ندارد)."""
    payment = Payment.objects.select_for_update().filter(authority=authority).first()
    if not payment:
        return None
    if payment.status != Payment.Status.PENDING:
        return payment
    if not ok:
        payment.status, payment.detail = Payment.Status.FAILED, "پرداخت انجام نشد یا لغو شد"
        payment.save(update_fields=["status", "detail"])
        _on_failed(payment)
        return payment
    ref = "MOCK"
    if payment.gateway == "zarinpal":
        try:
            r = _post_json(f"{_zarinpal_base()}/pg/v4/payment/verify.json", {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID, "amount": payment.amount, "authority": authority,
            })
            data = r.get("data") or {}
            if data.get("code") not in (100, 101):
                payment.status, payment.detail = Payment.Status.FAILED, json.dumps(r, ensure_ascii=False)[:300]
                payment.save(update_fields=["status", "detail"])
                _on_failed(payment)
                return payment
            ref = str(data.get("ref_id", ""))
        except Exception as e:  # noqa: BLE001
            # نتیجه نامعلوم است؛ پرداخت در انتظار می‌ماند تا با تلاش دوباره تعیین تکلیف شود
            log.exception("zarinpal verify failed")
            payment.detail = f"{type(e).__name__}: {e}"[:300]
            payment.save(update_fields=["detail"])
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
        order_services.mark_order_paid(payment.order)


def _on_failed(payment: Payment) -> None:
    from . import order_services

    if payment.order_id:
        order_services.release_unpaid_order(payment.order, "پرداخت ناموفق")
