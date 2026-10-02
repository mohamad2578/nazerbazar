"""قواعد اصلی بازار:
1. فروشگاه فقط می‌تواند بین «نرخ اتحادیه» و «نرخ اتحادیه منهای حداکثر تخفیف» (پیش‌فرض ۲۰٪) قیمت بدهد.
2. اگر اتحادیه نرخ را تغییر دهد و فروشگاه ظرف مهلت (پیش‌فرض ۲۴ ساعت) قیمتش را تایید/به‌روز نکند،
   آن کالا در آن فروشگاه موقتا از فهرست عمومی حذف می‌شود تا به‌روزرسانی انجام شود.
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Min, Q
from django.utils import timezone

from apps.accounts.models import User, notify
from apps.core.utils import percent_change
from apps.orgs.models import Store

from .models import DailySnapshot, OfferLog, OfficialPrice, Product, StoreOffer


def grace_period() -> timedelta:
    return timedelta(hours=settings.MARKET["UPDATE_GRACE_HOURS"])


def visible_offers(now=None):
    """قیمت‌هایی که در سایت عمومی نمایش داده می‌شوند."""
    now = now or timezone.now()
    fresh = Q(product__price_changed_at__isnull=True) | Q(confirmed_at__gte=F("product__price_changed_at"))
    in_grace = Q(product__price_changed_at__gt=now - grace_period())
    return StoreOffer.objects.filter(
        fresh | in_grace,
        is_available=True,
        store__status=Store.Status.ACTIVE,
        product__is_active=True,
        product__current_price__gt=0,
    )


def validate_offer_price(product: Product, price: int) -> None:
    if not product.current_price:
        raise ValidationError({"price": "اتحادیه هنوز نرخی برای این کالا تعیین نکرده است."})
    if price > product.current_price:
        raise ValidationError({"price": f"قیمت نمی‌تواند بیشتر از نرخ اتحادیه ({product.current_price:,} ریال) باشد."})
    if price < product.min_allowed_price:
        raise ValidationError(
            {
                "price": f"حداکثر {product.max_discount_percent}٪ کمتر از نرخ اتحادیه مجاز است "
                f"(حداقل {product.min_allowed_price:,} ریال)."
            }
        )


@transaction.atomic
def set_official_price(product: Product, price: int, by: User, max_discount=None, note="") -> OfficialPrice:
    price = int(price)
    if price <= 0:
        raise ValidationError({"price": "نرخ باید بزرگ‌تر از صفر باشد."})
    if max_discount is not None:
        product.max_discount_percent = int(max_discount)
    previous = product.current_price
    changed = previous != price
    record = OfficialPrice.objects.create(
        product=product,
        price=price,
        previous_price=previous,
        max_discount_percent=product.max_discount_percent,
        note=note,
        set_by=by,
    )
    product.current_price = price
    if changed:
        product.price_changed_at = record.created_at
    product.save(update_fields=["current_price", "max_discount_percent", "price_changed_at", "updated_at"])

    if changed and previous:
        hours = settings.MARKET["UPDATE_GRACE_HOURS"]
        owners = User.objects.filter(stores__offers__product=product).distinct()
        notify(
            owners,
            f"تغییر نرخ «{product.name}»",
            f"نرخ جدید {price:,} ریال است. ظرف {hours} ساعت قیمت خود را به‌روز کنید؛ "
            "در غیر این صورت این کالا موقتا از فهرست فروشگاه شما حذف می‌شود.",
            "/panel/prices",
        )
        change = percent_change(previous, price)
        if change is not None and abs(change) >= settings.MARKET["ALERT_CHANGE_PERCENT"]:
            from apps.observatory.services import raise_official_price_alert

            raise_official_price_alert(product, previous, price, change)
    return record


@transaction.atomic
def upsert_offer(store: Store, product: Product, price: int, is_available=True) -> StoreOffer:
    if store.status != Store.Status.ACTIVE:
        raise ValidationError({"store": "فروشگاه شما هنوز فعال نشده است."})
    if product.union_id != store.union_id:
        raise ValidationError({"product": "این کالا متعلق به اتحادیه شما نیست."})
    if not product.is_active:
        raise ValidationError({"product": "این کالا غیرفعال است."})
    price = int(price)
    validate_offer_price(product, price)
    now = timezone.now()
    offer, created = StoreOffer.objects.select_for_update().get_or_create(
        store=store, product=product, defaults={"price": price, "is_available": is_available, "confirmed_at": now}
    )
    if not created:
        offer.price, offer.is_available, offer.confirmed_at = price, is_available, now
        offer.save()
    OfferLog.objects.create(offer=offer, price=price, official_price=product.current_price)
    return offer


def take_daily_snapshot(date=None) -> int:
    """میانگین/کمینه/بیشینه قیمت هر کالا در هر شهرستان؛ روزانه با cron اجرا شود."""
    date = date or timezone.localdate()
    now = timezone.now()
    visible_ids = set(visible_offers(now).values_list("pk", flat=True))
    rows = (
        StoreOffer.objects.filter(is_available=True, store__status=Store.Status.ACTIVE, product__is_active=True)
        .values("product_id", "product__current_price", county_id=F("store__union__chamber__county_id"))
        .annotate(
            mn=Min("price", filter=Q(pk__in=visible_ids)),
            av=Avg("price", filter=Q(pk__in=visible_ids)),
            mx=Max("price", filter=Q(pk__in=visible_ids)),
            cnt=Count("pk", filter=Q(pk__in=visible_ids)),
            total=Count("pk"),
        )
    )
    n = 0
    seen = set()
    for r in rows:
        seen.add((r["product_id"], r["county_id"]))
        DailySnapshot.objects.update_or_create(
            date=date,
            product_id=r["product_id"],
            county_id=r["county_id"],
            defaults=dict(
                official_price=r["product__current_price"],
                min_price=r["mn"],
                avg_price=int(r["av"]) if r["av"] else None,
                max_price=r["mx"],
                offer_count=r["cnt"],
                stale_count=r["total"] - r["cnt"],
            ),
        )
        n += 1
    # کالاهای بدون عرضه هم با نرخ مصوب ثبت شوند تا روند نرخ رسمی کامل باشد
    for p in Product.objects.filter(is_active=True, current_price__gt=0).select_related("union__chamber"):
        key = (p.pk, p.union.chamber.county_id)
        if key not in seen:
            DailySnapshot.objects.update_or_create(
                date=date, product=p, county_id=key[1], defaults=dict(official_price=p.current_price)
            )
            n += 1
    return n
