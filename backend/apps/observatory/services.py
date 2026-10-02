from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import Role, User, notify
from apps.core.utils import percent_change
from apps.market.models import DailySnapshot, Product, StoreOffer

from .models import Alert, Commodity


def _create_alert(dedupe_key: str, **fields) -> Alert | None:
    """از ثبت هشدار تکراری در یک روز جلوگیری می‌کند."""
    key = f"{timezone.localdate()}:{dedupe_key}"
    if Alert.objects.filter(dedupe_key=key).exists():
        return None
    return Alert.objects.create(dedupe_key=key, **fields)


def _level(change: float) -> str:
    return Alert.Level.CRITICAL if abs(change) >= 2 * settings.MARKET["ALERT_CHANGE_PERCENT"] else Alert.Level.WARNING


def raise_official_price_alert(product: Product, old: int, new: int, change: float):
    county = product.union.chamber.county
    alert = _create_alert(
        f"official:{product.pk}:{new}",
        kind=Alert.Kind.OFFICIAL_JUMP,
        level=_level(change),
        title=f"تغییر {change:+.1f}٪ نرخ مصوب «{product.name}»",
        message=f"از {old:,} به {new:,} ریال توسط {product.union.name}",
        product=product,
        county=county,
        change_percent=change,
    )
    if alert:
        notify(
            User.objects.filter(Q(role=Role.CHAMBER, chamber=product.union.chamber) | Q(role=Role.GOVERNORATE, province=county.province)),
            alert.title,
            alert.message,
            "/panel/alerts",
        )


def scan_alerts(today=None) -> int:
    """اجرای روزانه پس از snapshot: جهش قیمت بازار، کاهش عرضه، قیمت‌های به‌روزنشده، افزایش شکایات."""
    today = today or timezone.localdate()
    week_ago = today - timedelta(days=7)
    threshold = settings.MARKET["ALERT_CHANGE_PERCENT"]
    created = 0
    past = {
        (s.product_id, s.county_id): s
        for s in DailySnapshot.objects.filter(date=week_ago)
    }
    for s in DailySnapshot.objects.filter(date=today).select_related("product", "county"):
        old = past.get((s.product_id, s.county_id))
        if not old:
            continue
        if s.avg_price and old.avg_price:
            ch = percent_change(old.avg_price, s.avg_price)
            if ch is not None and abs(ch) >= threshold:
                created += bool(_create_alert(
                    f"market:{s.product_id}:{s.county_id}",
                    kind=Alert.Kind.MARKET_JUMP, level=_level(ch),
                    title=f"تغییر {ch:+.1f}٪ میانگین قیمت «{s.product.name}» در {s.county.name} طی یک هفته",
                    product=s.product, county=s.county, change_percent=ch,
                ))
        if old.offer_count >= 4 and s.offer_count <= old.offer_count / 2:
            created += bool(_create_alert(
                f"shortage:{s.product_id}:{s.county_id}",
                kind=Alert.Kind.SHORTAGE, level=Alert.Level.CRITICAL if s.offer_count == 0 else Alert.Level.WARNING,
                title=f"کاهش عرضه «{s.product.name}» در {s.county.name}",
                message=f"تعداد فروشگاه‌های عرضه‌کننده از {old.offer_count} به {s.offer_count} رسید.",
                product=s.product, county=s.county,
            ))
        if s.stale_count and s.stale_count >= max(3, s.offer_count):
            created += bool(_create_alert(
                f"stale:{s.product_id}:{s.county_id}",
                kind=Alert.Kind.STALE, level=Alert.Level.INFO,
                title=f"{s.stale_count} فروشگاه قیمت «{s.product.name}» را پس از تغییر نرخ به‌روز نکرده‌اند",
                product=s.product, county=s.county,
            ))
    from apps.complaints.models import Complaint

    hot = (
        Complaint.objects.filter(created_at__date__gte=week_ago, store__isnull=False)
        .values("store").annotate(n=Count("pk")).filter(n__gte=3)
    )
    from apps.orgs.models import Store

    for row in hot:
        st = Store.objects.select_related("union__chamber__county").get(pk=row["store"])
        created += bool(_create_alert(
            f"complaints:{st.pk}",
            kind=Alert.Kind.COMPLAINTS, level=Alert.Level.WARNING,
            title=f"{row['n']} شکایت از «{st.name}» در یک هفته اخیر",
            store=st, county=st.union.chamber.county,
        ))
    return created


def commodity_unit_prices(county_ids=None, date=None):
    """میانگین قیمت هر واحد کالای اساسی بر اساس snapshot یک روز (یا قیمت‌های زنده)."""
    per = defaultdict(list)
    if date:
        qs = DailySnapshot.objects.filter(date=date, product__commodity__isnull=False).select_related("product")
        if county_ids:
            qs = qs.filter(county_id__in=county_ids)
        for s in qs:
            price = s.avg_price or s.official_price
            per[s.product.commodity_id].append(price / float(s.product.unit_amount or 1))
    else:
        from apps.market.services import visible_offers

        qs = visible_offers().filter(product__commodity__isnull=False).select_related("product")
        if county_ids:
            qs = qs.filter(store__union__chamber__county_id__in=county_ids)
        for o in qs:
            per[o.product.commodity_id].append(o.price / float(o.product.unit_amount or 1))
        official = Product.objects.filter(commodity__isnull=False, is_active=True, current_price__gt=0)
        if county_ids:
            official = official.filter(union__chamber__county_id__in=county_ids)
        for p in official:
            if p.commodity_id not in per:
                per[p.commodity_id].append(p.current_price / float(p.unit_amount or 1))
    return {cid: sum(v) / len(v) for cid, v in per.items() if v}


def basket_cost(county_ids=None, date=None) -> dict:
    """هزینه ماهانه سبد خانوار از قیمت واقعی فروشگاه‌ها (ماژول داشبورد رفاه)."""
    prices = commodity_unit_prices(county_ids, date)
    items, total, covered = [], 0.0, 0
    basket = Commodity.objects.filter(basket_monthly_qty__gt=0)
    for c in basket:
        unit_price = prices.get(c.pk)
        cost = float(c.basket_monthly_qty) * unit_price if unit_price else None
        if cost:
            total += cost
            covered += 1
        items.append({
            "commodity": c.name, "qty": float(c.basket_monthly_qty), "unit": c.unit,
            "unit_price": round(unit_price) if unit_price else None, "cost": round(cost) if cost else None,
        })
    return {"total": round(total), "covered": covered, "items_count": basket.count(), "items": items}


def stale_offer_count(qs=None) -> int:
    from apps.market.services import grace_period

    qs = qs if qs is not None else StoreOffer.objects.all()
    from django.db.models import F

    return qs.filter(
        product__price_changed_at__isnull=False,
        confirmed_at__lt=F("product__price_changed_at"),
        product__price_changed_at__lte=timezone.now() - grace_period(),
    ).count()
