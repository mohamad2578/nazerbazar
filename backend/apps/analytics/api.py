"""گزارش‌های تحلیلی پنل‌ها؛ همه خروجی‌ها به حوزه دسترسی کاربر محدود می‌شوند."""
from collections import defaultdict
from datetime import timedelta
from io import BytesIO

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.complaints.models import Complaint
from apps.core.permissions import role_permission
from apps.core.scoping import scoped
from apps.core.utils import percent_change
from apps.distribution.models import Allocation, Quota
from apps.market.models import DailySnapshot, OfficialPrice, Product, StoreOffer
from apps.market.services import grace_period, visible_offers
from apps.observatory.models import Alert
from apps.observatory.services import basket_cost
from apps.orgs.models import County, Store, Union

PANEL = role_permission("governorate", "chamber", "union", "store")
MANAGERS = role_permission("governorate", "chamber", "union")


def S(qs, request):
    return scoped(qs, request.user, qs.model.SCOPE)


def _days(request, default=30):
    try:
        return max(1, min(365, int(request.query_params.get("days", default))))
    except ValueError:
        return default


def _hours(td):
    return round(td.total_seconds() / 3600, 1) if td else None


def _resolution_expr():
    return ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())


@api_view(["GET"])
@permission_classes([PANEL])
def overview(request):
    now = timezone.now()
    stores = S(Store.objects.all(), request)
    offers = S(StoreOffer.objects.all(), request)
    products = S(Product.objects.filter(is_active=True), request)
    complaints = S(Complaint.objects.all(), request)
    visible = offers.filter(pk__in=visible_offers(now).values("pk")).count()
    total_offers = offers.filter(is_available=True, store__status=Store.Status.ACTIVE).count()
    hidden_stale = offers.filter(
        product__price_changed_at__isnull=False,
        confirmed_at__lt=F("product__price_changed_at"),
        product__price_changed_at__lte=now - grace_period(),
    ).count()
    status_counts = dict(stores.values_list("status").annotate(c=Count("pk")))
    c_status = dict(complaints.values_list("status").annotate(c=Count("pk")))
    resolved = complaints.filter(resolved_at__isnull=False)
    avg_res = resolved.aggregate(v=Avg(_resolution_expr()))["v"]
    changes = S(OfficialPrice.objects.all(), request)
    discount = offers.filter(product__current_price__gt=0).aggregate(
        v=Avg((F("product__current_price") - F("price")) * 100.0 / F("product__current_price"))
    )["v"]
    return Response({
        "stores": {
            "total": stores.count(), "active": status_counts.get("active", 0), "pending": status_counts.get("pending", 0),
            "suspended": status_counts.get("suspended", 0), "rejected": status_counts.get("rejected", 0),
            "verified": stores.filter(is_verified=True).count(),
        },
        "products": {"total": products.count(), "priced": products.filter(current_price__gt=0).count()},
        "offers": {
            "total": total_offers, "visible": visible, "hidden_stale": hidden_stale,
            "compliance_percent": round(visible / total_offers * 100, 1) if total_offers else None,
            "avg_discount_percent": round(discount, 1) if discount is not None else None,
        },
        "complaints": {
            "total": complaints.count(),
            "open": sum(v for k, v in c_status.items() if k in ("new", "reviewing", "inspection")),
            "new": c_status.get("new", 0), "resolved": c_status.get("resolved", 0),
            "rejected": c_status.get("rejected", 0),
            "violations": complaints.filter(violation_confirmed=True).count(),
            "avg_resolution_hours": _hours(avg_res),
            "last_7_days": complaints.filter(created_at__gte=now - timedelta(days=7)).count(),
        },
        "price_changes": {
            "last_7_days": changes.filter(created_at__gte=now - timedelta(days=7), previous_price__gt=0).count(),
            "last_30_days": changes.filter(created_at__gte=now - timedelta(days=30), previous_price__gt=0).count(),
        },
        "alerts_open": S(Alert.objects.filter(is_resolved=False), request).count(),
        "rating_avg": stores.filter(rating_count__gt=0).aggregate(v=Avg("rating_avg"))["v"],
    })


@api_view(["GET"])
@permission_classes([PANEL])
def trends(request):
    """روند قیمت: برای یک کالا (مصوب/میانگین/کمینه/بیشینه بازار) یا شاخص کل (پایه=۱۰۰)"""
    days = _days(request)
    since = timezone.localdate() - timedelta(days=days)
    snaps = S(DailySnapshot.objects.filter(date__gte=since), request)
    if county := request.query_params.get("county"):
        snaps = snaps.filter(county_id=county)
    if pid := request.query_params.get("product"):
        rows = snaps.filter(product_id=pid).values("date").annotate(
            official=Avg("official_price"), avg=Avg("avg_price"), min=Avg("min_price"), max=Avg("max_price"),
            offers=Sum("offer_count"),
        ).order_by("date")
        series = [{k: (round(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]
        history = S(OfficialPrice.objects.filter(product_id=pid, created_at__date__gte=since), request)
        return Response({"series": series, "changes": list(history.values("price", "previous_price", "created_at"))})
    if commodity := request.query_params.get("commodity"):
        snaps = snaps.filter(product__commodity_id=commodity)
    # شاخص قیمت: میانگین نسبت قیمت هر کالا به قیمت روز اول آن
    base_official, base_market = {}, {}
    acc = defaultdict(lambda: {"o": [], "m": []})
    for s in snaps.order_by("date").values("date", "product_id", "county_id", "official_price", "avg_price"):
        key = (s["product_id"], s["county_id"])
        base_official.setdefault(key, s["official_price"])
        if s["official_price"] and base_official[key]:
            acc[s["date"]]["o"].append(s["official_price"] / base_official[key] * 100)
        if s["avg_price"]:
            base_market.setdefault(key, s["avg_price"])
            acc[s["date"]]["m"].append(s["avg_price"] / base_market[key] * 100)
    series = [
        {"date": d, "official_index": round(sum(v["o"]) / len(v["o"]), 2) if v["o"] else None,
         "market_index": round(sum(v["m"]) / len(v["m"]), 2) if v["m"] else None}
        for d, v in sorted(acc.items())
    ]
    return Response({"series": series})


@api_view(["GET"])
@permission_classes([PANEL])
def price_changes(request):
    """بیشترین تغییرات نرخ مصوب در بازه (Top movers)"""
    days = _days(request)
    qs = S(OfficialPrice.objects.filter(created_at__gte=timezone.now() - timedelta(days=days), previous_price__gt=0), request)
    rows = [
        {"product": r.product_id, "product_name": r.product.name, "union_name": r.product.union.name,
         "previous_price": r.previous_price, "price": r.price, "change_percent": percent_change(r.previous_price, r.price),
         "created_at": r.created_at}
        for r in qs.select_related("product__union")[:500]
    ]
    rows.sort(key=lambda r: -abs(r["change_percent"] or 0))
    return Response(rows[:50])


@api_view(["GET"])
@permission_classes([PANEL])
def complaints_report(request):
    days = _days(request, 90)
    since = timezone.now() - timedelta(days=days)
    qs = S(Complaint.objects.filter(created_at__gte=since), request)
    by_day = list(qs.annotate(d=TruncDate("created_at")).values("d").annotate(c=Count("pk")).order_by("d"))
    by_union = []
    for r in qs.values("union", "union__name").annotate(
        total=Count("pk"),
        resolved=Count("pk", filter=Q(status="resolved")),
        open=Count("pk", filter=Q(status__in=["new", "reviewing", "inspection"])),
        violations=Count("pk", filter=Q(violation_confirmed=True)),
        avg_res=Avg(_resolution_expr()),
    ).order_by("-total"):
        by_union.append({**r, "union__name": r["union__name"] or "فروشندگان خارج از سامانه", "avg_res": _hours(r["avg_res"])})
    top_stores = list(
        qs.filter(store__isnull=False).values("store", "store__name", "store__union__name")
        .annotate(c=Count("pk"), v=Count("pk", filter=Q(violation_confirmed=True))).order_by("-c")[:10]
    )
    top_products = list(
        qs.filter(product__isnull=False).values("product__name").annotate(c=Count("pk")).order_by("-c")[:10]
    )
    kind_labels = dict(Complaint.Kind.choices)
    status_labels = dict(Complaint.Status.choices)
    return Response({
        "by_day": [{"date": r["d"], "count": r["c"]} for r in by_day],
        "by_status": [{"key": k, "label": status_labels[k], "count": c} for k, c in qs.values_list("status").annotate(c=Count("pk"))],
        "by_kind": [{"key": k, "label": kind_labels[k], "count": c} for k, c in qs.values_list("kind").annotate(c=Count("pk"))],
        "by_union": by_union, "top_stores": top_stores, "top_products": top_products,
    })


def _union_rows(request):
    now = timezone.now()
    unions = S(Union.objects.select_related("chamber__county"), request)
    rows = []
    for u in unions:
        offers = StoreOffer.objects.filter(store__union=u, is_available=True, store__status=Store.Status.ACTIVE)
        total = offers.count()
        visible = visible_offers(now).filter(store__union=u).count()
        cq = Complaint.objects.filter(union=u)
        rows.append({
            "id": u.pk, "name": u.name, "county": u.chamber.county.name,
            "products": u.products.filter(is_active=True).count(),
            "stores_active": u.stores.filter(status=Store.Status.ACTIVE).count(),
            "stores_pending": u.stores.filter(status=Store.Status.PENDING).count(),
            "offers": total, "compliance_percent": round(visible / total * 100, 1) if total else None,
            "price_changes_30d": OfficialPrice.objects.filter(
                product__union=u, previous_price__gt=0, created_at__gte=now - timedelta(days=30)
            ).count(),
            "complaints": cq.count(),
            "complaints_open": cq.filter(status__in=["new", "reviewing", "inspection"]).count(),
            "avg_resolution_hours": _hours(cq.filter(resolved_at__isnull=False).aggregate(v=Avg(_resolution_expr()))["v"]),
        })
    return rows


@api_view(["GET"])
@permission_classes([MANAGERS])
def unions_report(request):
    return Response(_union_rows(request))


def _county_rows(request):
    counties = S(County.objects.select_related("province"), request)
    if request.user.role in ("union",):
        counties = County.objects.filter(pk=request.user.union.chamber.county_id)
    rows = []
    for c in counties:
        stores = Store.objects.filter(union__chamber__county=c)
        offers = StoreOffer.objects.filter(store__union__chamber__county=c, store__status=Store.Status.ACTIVE)
        disc = offers.filter(product__current_price__gt=0).aggregate(
            v=Avg((F("product__current_price") - F("price")) * 100.0 / F("product__current_price"))
        )["v"]
        basket = basket_cost([c.pk])
        rows.append({
            "id": c.pk, "name": c.name, "province": c.province.name, "population": c.population,
            "stores_active": stores.filter(status=Store.Status.ACTIVE).count(),
            "offers": offers.count(), "avg_discount_percent": round(disc, 1) if disc is not None else None,
            "complaints": Complaint.objects.filter(chamber__county=c).count(),
            "basket_total": basket["total"], "basket_coverage": f'{basket["covered"]}/{basket["items_count"]}',
            "stores_per_10k": round(stores.filter(status=Store.Status.ACTIVE).count() / c.population * 10000, 2)
            if c.population else None,
        })
    return rows


@api_view(["GET"])
@permission_classes([MANAGERS])
def counties_report(request):
    return Response(_county_rows(request))


@api_view(["GET"])
@permission_classes([PANEL])
def basket_report(request):
    """هزینه سبد خانوار: وضعیت فعلی و روند (بر اساس snapshot روزانه)"""
    days = _days(request, 90)
    county = request.query_params.get("county")
    counties = [int(county)] if county else list(S(County.objects.all(), request).values_list("pk", flat=True)) \
        if request.user.role in ("governorate", "chamber") else None
    dates = DailySnapshot.objects.filter(date__gte=timezone.localdate() - timedelta(days=days)).dates("date", "day")
    step = max(1, len(dates) // 30)
    series = []
    for d in list(dates)[::step]:
        b = basket_cost(counties, d)
        series.append({"date": d, "total": b["total"], "covered": b["covered"]})
    return Response({"current": basket_cost(counties), "series": series})


@api_view(["GET"])
@permission_classes([MANAGERS])
def distribution_report(request):
    allocs = S(Allocation.objects.select_related("commodity"), request).distinct()
    rows = []
    for a in allocs:
        q = Quota.objects.filter(share__allocation=a).exclude(status=Quota.Status.CANCELED)
        agg = q.aggregate(assigned=Sum("quantity"), received=Sum("received_quantity"), sold=Sum("sold_quantity"))
        dispatched = q.filter(status__in=["received", "sold_out"]).aggregate(v=Sum("quantity"))["v"] or 0
        received = float(agg["received"] or 0)
        rows.append({
            "id": a.pk, "title": a.title, "commodity": a.commodity.name, "status": a.get_status_display(),
            "total": float(a.total_quantity), "assigned": float(agg["assigned"] or 0), "received": received,
            "sold": float(agg["sold"] or 0),
            "delivery_gap": round(float(dispatched) - received, 2),
            "delivery_gap_percent": round((float(dispatched) - received) / float(dispatched) * 100, 1) if dispatched else None,
            "allocation_price": a.allocation_price, "consumer_price": a.consumer_price,
            "stores": q.values("store").distinct().count(),
        })
    return Response(rows)


# ───────────────────────── خروجی اکسل ─────────────────────────

EXPORTS = {
    "unions": ("عملکرد اتحادیه‌ها", _union_rows, [
        ("name", "اتحادیه"), ("county", "شهرستان"), ("products", "کالا"), ("stores_active", "فروشگاه فعال"),
        ("stores_pending", "در انتظار"), ("offers", "قیمت ثبت‌شده"), ("compliance_percent", "انطباق٪"),
        ("price_changes_30d", "تغییر نرخ ۳۰ روز"), ("complaints", "شکایات"), ("complaints_open", "شکایت باز"),
        ("avg_resolution_hours", "میانگین رسیدگی (ساعت)"),
    ]),
    "counties": ("وضعیت شهرستان‌ها", _county_rows, [
        ("name", "شهرستان"), ("province", "استان"), ("stores_active", "فروشگاه فعال"), ("offers", "قیمت ثبت‌شده"),
        ("avg_discount_percent", "میانگین تخفیف٪"), ("complaints", "شکایات"), ("basket_total", "سبد خانوار (ریال)"),
        ("stores_per_10k", "فروشگاه به ازای ۱۰هزار نفر"),
    ]),
    "stores": ("فروشگاه‌ها", lambda r: [
        {"name": s.name, "union": s.union.name, "status": s.get_status_display(), "phone": s.phone,
         "address": s.address, "owner": s.owner.full_name, "mobile": s.owner.mobile, "rating": float(s.rating_avg),
         "offers": s.offers.count(), "complaints": s.complaints.count()}
        for s in S(Store.objects.select_related("union", "owner"), r)
    ], [
        ("name", "فروشگاه"), ("union", "اتحادیه"), ("status", "وضعیت"), ("owner", "مالک"), ("mobile", "موبایل"),
        ("phone", "تلفن"), ("address", "نشانی"), ("rating", "امتیاز"), ("offers", "تعداد قیمت"), ("complaints", "شکایات"),
    ]),
    "prices": ("نرخ‌های مصوب", lambda r: [
        {"name": p.name, "union": p.union.name, "unit": p.get_unit_display(), "price": p.current_price,
         "min": p.min_allowed_price, "changed": timezone.localtime(p.price_changed_at).strftime("%Y-%m-%d %H:%M") if p.price_changed_at else ""}
        for p in S(Product.objects.filter(is_active=True).select_related("union"), r)
    ], [
        ("name", "کالا"), ("union", "اتحادیه"), ("unit", "واحد"), ("price", "نرخ مصوب (ریال)"),
        ("min", "حداقل مجاز (ریال)"), ("changed", "آخرین تغییر"),
    ]),
    "complaints": ("شکایات", lambda r: [
        {"code": c.tracking_code, "kind": c.get_kind_display(), "status": c.get_status_display(),
         "store": c.store.name if c.store else c.shop_name, "product": c.product.name if c.product else "",
         "union": c.union.name if c.union else "", "paid": c.paid_price, "official": c.official_price,
         "violation": {True: "بله", False: "خیر"}.get(c.violation_confirmed, ""),
         "created": timezone.localtime(c.created_at).strftime("%Y-%m-%d %H:%M")}
        for c in S(Complaint.objects.select_related("store", "product", "union"), r)[:5000]
    ], [
        ("code", "کد رهگیری"), ("kind", "نوع"), ("status", "وضعیت"), ("store", "فروشگاه"), ("product", "کالا"),
        ("union", "اتحادیه"), ("paid", "قیمت دریافتی"), ("official", "نرخ مصوب"), ("violation", "تخلف محرز"),
        ("created", "زمان ثبت"),
    ]),
}


@api_view(["GET"])
@permission_classes([MANAGERS])
def export(request, name):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    if name not in EXPORTS:
        raise ValidationError({"detail": "گزارش نامعتبر است."})
    title, fn, cols = EXPORTS[name]
    wb = Workbook()
    ws = wb.active
    ws.title = title[:30]
    ws.sheet_view.rightToLeft = True
    ws.append([c[1] for c in cols])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0F766E")
    for row in fn(request):
        ws.append([row.get(c[0]) for c in cols])
    for i, _ in enumerate(cols, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = 22
    buf = BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{name}-{timezone.localdate()}.xlsx"'
    return resp
