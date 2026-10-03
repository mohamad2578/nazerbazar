from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from . import backup
from .permissions import role_permission

AdminOnly = role_permission("admin")


@api_view(["GET"])
@permission_classes([AdminOnly])
def status(request):
    """وضعیت فعلی داده‌ها برای نمایش در صفحه پشتیبان‌گیری."""
    return Response({"counts": backup.counts()})


@api_view(["GET"])
@permission_classes([AdminOnly])
def download(request):
    content, name = backup.create_backup()
    resp = HttpResponse(content, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@api_view(["POST"])
@permission_classes([AdminOnly])
@parser_classes([MultiPartParser])
def inspect(request):
    """پیش‌نمایش محتوای فایل پشتیبان، پیش از بازیابی."""
    f = request.FILES.get("file")
    if not f:
        raise ValidationError({"file": "فایل پشتیبان را انتخاب کنید."})
    try:
        return Response(backup.inspect(f))
    except Exception as e:  # noqa: BLE001 - پیام خطا برای کاربر
        raise ValidationError({"file": str(e) or "فایل قابل خواندن نیست."})


@api_view(["POST"])
@permission_classes([AdminOnly])
@parser_classes([MultiPartParser])
def restore(request):
    f = request.FILES.get("file")
    if not f:
        raise ValidationError({"file": "فایل پشتیبان را انتخاب کنید."})
    if request.data.get("confirm") not in ("true", "True", True, "1"):
        raise ValidationError({"confirm": "برای بازیابی باید جایگزینی اطلاعات را تایید کنید."})
    with_media = request.data.get("with_media", "true") not in ("false", "False", False, "0")
    try:
        return Response(backup.restore(f, with_media))
    except Exception as e:  # noqa: BLE001
        raise ValidationError({"file": str(e) or "بازیابی انجام نشد."})
