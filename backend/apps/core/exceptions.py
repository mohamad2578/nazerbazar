import decimal
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger(__name__)

# پیام‌های ValueError/OverflowError که از «ورودی نامعتبر کاربر» می‌آیند (مثلا ?county=abc یا عدد بسیار بزرگ)، نه خطای برنامه
_BAD_INPUT = ("expected a number", "invalid literal for int()", "too large to convert", "out of range", "Invalid ordering")


def handler(exc, context):
    # خطاهای اعتبارسنجی لایه سرویس (Django) هم به شکل 400 استاندارد برگردند
    if isinstance(exc, DjangoValidationError):
        exc = serializers.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        )
    resp = exception_handler(exc, context)
    if resp is None and (
        isinstance(exc, (DataError, decimal.InvalidOperation, OverflowError))
        or (isinstance(exc, (ValueError, TypeError)) and any(m in str(exc) for m in _BAD_INPUT))
    ):
        # ورودی خراب (عدد غیرمجاز، خارج از بازه ستون، متن بلندتر از حد) → ۴۰۰؛ ولی در لاگ می‌ماند تا بررسی شود
        log.warning("bad input rejected: %s: %s", type(exc).__name__, exc)
        return Response({"detail": "مقدار ورودی نامعتبر است."}, status=400)
    return resp
