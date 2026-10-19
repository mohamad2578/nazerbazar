from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.db.models.functions import ExtractHour, TruncDay, TruncHour
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.core.permissions import role_permission
from apps.market.models import Product
from apps.orgs.models import Store

from .models import Visit

# اپلیکیشن اندروید این عبارت را به user-agent اضافه می‌کند
APP_UA_MARK = "Nazer724App"


class TrackThrottle(AnonRateThrottle):
    """جلوگیری از پرکردن آمار با درخواست‌های انبوه؛ برای مرور عادی بسیار دست‌ودل‌باز است."""

    rate = "120/min"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([TrackThrottle])
def track(request):
    """ثبت یک بازدید صفحه یا کالا (فراخوانی از سایت و اپلیکیشن)."""
    data = request.data
    visitor = str(data.get("visitor") or "").strip()[:40]
    if not visitor:
        raise ValidationError({"visitor": "شناسه بازدیدکننده لازم است."})
    kind = data.get("kind") if data.get("kind") in Visit.Kind.values else Visit.Kind.PAGE
    product = None
    if kind == Visit.Kind.PRODUCT:
        product = Product.objects.filter(pk=data.get("product")).only("pk").first()
        if not product:
            return Response(status=204)
    ua = request.META.get("HTTP_USER_AGENT", "")
    Visit.objects.create(
        kind=kind,
        path=str(data.get("path") or "")[:300],
        product=product,
        visitor=visitor,
        user=request.user if request.user.is_authenticated else None,
        platform=Visit.Platform.APP if APP_UA_MARK in ua else Visit.Platform.WEB,
    )
    return Response(status=204)


def _range(request):
    """بازه گزارش از پارامترهای from/to (ISO)؛ پیش‌فرض ۷ روز گذشته."""
    now = timezone.now()

    def parse(name, default):
        raw = request.query_params.get(name)
        if not raw:
            return default
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            raise ValidationError({name: "تاریخ نامعتبر است."})
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    start = parse("from", now - timedelta(days=7))
    end = parse("to", now)
    if end <= start:
        raise ValidationError({"to": "پایان بازه باید بعد از شروع باشد."})
    return start, end


@api_view(["GET"])
@permission_classes([role_permission("samt", "governorate")])
def visits_report(request):
    """گزارش بازدید: کل بازدید، بازدیدکننده یکتا، روند زمانی، پربازدیدترین کالاها و ساعات اوج."""
    from apps.core.models import require_report

    require_report(request.user, "visits")
    start, end = _range(request)
    qs = Visit.objects.filter(created_at__gte=start, created_at__lt=end)
    pages = qs.filter(kind=Visit.Kind.PAGE)
    products = qs.filter(kind=Visit.Kind.PRODUCT)

    # تفکیک ساعتی برای بازه‌های تا ۳ روز، روزانه برای بقیه
    hourly = (end - start) <= timedelta(days=3)
    trunc = TruncHour if hourly else TruncDay
    # با ?product=<id> روند فقط کلیک‌های همان کالا را نشان می‌دهد
    focus = request.query_params.get("product")
    base = products.filter(product_id=focus) if focus else pages
    series = (
        base.annotate(t=trunc("created_at")).values("t")
        .annotate(views=Count("pk"), visitors=Count("visitor", distinct=True)).order_by("t")
    )
    # همه کالاها، حتی آن‌هایی که هیچ کلیکی نداشته‌اند، تا دقیقا معلوم باشد کدام دیده نشده
    in_range = Q(visits__kind=Visit.Kind.PRODUCT, visits__created_at__gte=start, visits__created_at__lt=end)
    all_products = (
        Product.objects.filter(is_active=True).select_related("union")
        .annotate(views=Count("visits", filter=in_range),
                  visitors=Count("visits__visitor", filter=in_range, distinct=True))
        .order_by("-views", "name")
    )
    # بازدید صفحه هر فروشگاه (مسیر /s/<id>)
    store_rows = (
        pages.filter(path__regex=r"^/s/[0-9]+$").values("path")
        .annotate(views=Count("pk"), visitors=Count("visitor", distinct=True)).order_by("-views")[:30]
    )
    store_ids = [int(r["path"].rsplit("/", 1)[1]) for r in store_rows]
    store_names = dict(Store.objects.filter(pk__in=store_ids).values_list("pk", "name"))
    by_hour = pages.annotate(h=ExtractHour("created_at")).values("h").annotate(views=Count("pk")).order_by("h")
    top_pages = pages.values("path").annotate(views=Count("pk")).order_by("-views")[:15]
    by_platform = dict(pages.values_list("platform").annotate(n=Count("pk")))

    return Response({
        "from": start, "to": end, "granularity": "hour" if hourly else "day",
        "page_views": pages.count(),
        "visitors": pages.values("visitor").distinct().count(),
        "product_views": products.count(),
        "logged_in_visitors": pages.exclude(user=None).values("user").distinct().count(),
        "platform": {"web": by_platform.get("web", 0), "app": by_platform.get("app", 0)},
        "series": [{"t": r["t"], "views": r["views"], "visitors": r["visitors"]} for r in series],
        "by_hour": [{"h": r["h"], "views": r["views"]} for r in by_hour],
        "focus_product": int(focus) if focus else None,
        "top_products": [
            {"id": p.pk, "name": p.name, "union": p.union.name, "views": p.views, "visitors": p.visitors}
            for p in all_products
        ],
        "top_stores": [
            {"id": int(r["path"].rsplit("/", 1)[1]), "name": store_names.get(int(r["path"].rsplit("/", 1)[1]), "—"),
             "views": r["views"], "visitors": r["visitors"]}
            for r in store_rows
        ],
        "top_pages": list(top_pages),
    })
