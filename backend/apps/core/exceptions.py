from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.views import exception_handler


def handler(exc, context):
    # خطاهای اعتبارسنجی لایه سرویس (Django) هم به شکل 400 استاندارد برگردند
    if isinstance(exc, DjangoValidationError):
        exc = serializers.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        )
    return exception_handler(exc, context)
