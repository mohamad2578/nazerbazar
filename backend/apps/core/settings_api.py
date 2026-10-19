from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import SAMT_REPORTS, UNION_SECTIONS, SystemSettings


def _payload(s: SystemSettings) -> dict:
    return {
        "union_can_set_prices": s.union_can_set_prices,
        "snap_store_prices": s.snap_store_prices,
        "union_sections": [k for k in (s.union_sections or []) if k in UNION_SECTIONS],
        "sections": [{"key": k, "label": v} for k, v in UNION_SECTIONS.items()],
        "samt_reports": s.samt_reports,
        "reports": [{"key": k, "label": v} for k, v in SAMT_REPORTS.items()],
        "updated_at": s.updated_at,
        "updated_by": s.updated_by.full_name if s.updated_by else "",
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def system_settings(request):
    """تنظیمات سامانه: همه کاربران پنل می‌خوانند (برای نمایش منو)، فقط مدیر کل تغییر می‌دهد."""
    s = SystemSettings.get()
    if request.method == "PATCH":
        if request.user.role != "admin":
            raise PermissionDenied("فقط مدیر کل سامانه می‌تواند تنظیمات را تغییر دهد.")
        data = request.data
        for field in ("union_can_set_prices", "snap_store_prices"):
            if field in data:
                setattr(s, field, data[field] in (True, "true", "True", 1, "1"))
        if "union_sections" in data:
            sections = data["union_sections"]
            if not isinstance(sections, list) or any(k not in UNION_SECTIONS for k in sections):
                raise ValidationError({"union_sections": "فهرست بخش‌ها نامعتبر است."})
            s.union_sections = sections
        if "samt_reports" in data:
            reports = data["samt_reports"]
            if not isinstance(reports, list) or any(k not in SAMT_REPORTS for k in reports):
                raise ValidationError({"samt_reports": "فهرست گزارش‌ها نامعتبر است."})
            s.samt_reports = reports
        s.updated_by = request.user
        s.save()
    return Response(_payload(s))
