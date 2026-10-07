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

from apps.accounts.models import Role, User, notify
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


# نقش‌هایی که نرخ مصوبشان بدون تایید اعمال می‌شود (اداره صمت بالادست اتاق اصناف است)
SELF_APPROVING_ROLES = (Role.SAMT, Role.CHAMBER, Role.GOVERNORATE, Role.ADMIN)
# نقش‌هایی که می‌توانند نرخ در انتظار را تایید یا رد کنند
PRICE_REVIEWER_ROLES = (Role.CHAMBER, Role.SAMT, Role.GOVERNORATE, Role.ADMIN)


@transaction.atomic
def set_official_price(product: Product, price: int, by: User, max_discount=None, note="") -> OfficialPrice:
    """ثبت نرخ مصوب.

    اگر ثبت‌کننده «اتحادیه» باشد، نرخ در وضعیت «در انتظار تایید» می‌ماند و تا تایید
    اتاق اصناف اعمال نمی‌شود. برای اداره صمت و بالاتر، بی‌درنگ اعمال می‌شود.
    """
    price = int(price)
    if price <= 0:
        raise ValidationError({"price": "نرخ باید بزرگ‌تر از صفر باشد."})

    needs_review = getattr(by, "role", None) not in SELF_APPROVING_ROLES
    discount = int(max_discount) if max_discount is not None else product.max_discount_percent

    record = OfficialPrice.objects.create(
        product=product,
        price=price,
        previous_price=product.current_price,
        max_discount_percent=discount,
        note=note,
        set_by=by,
        status=OfficialPrice.Status.PENDING if needs_review else OfficialPrice.Status.APPROVED,
    )

    if needs_review:
        # نرخ قبلی تا زمان تایید دست‌نخورده می‌ماند
        OfficialPrice.objects.filter(
            product=product, status=OfficialPrice.Status.PENDING
        ).exclude(pk=record.pk).update(
            status=OfficialPrice.Status.REJECTED,
            review_note="با ثبت نرخ جدیدتر توسط اتحادیه جایگزین شد.",
            reviewed_at=timezone.now(),
        )
        reviewers = User.objects.filter(
            Q(role=Role.CHAMBER, chamber=product.union.chamber)
            | Q(role=Role.SAMT, province=product.union.chamber.county.province)
        )
        notify(
            reviewers,
            f"نرخ جدید در انتظار تایید: {product.name}",
            f"{product.union.name} نرخ {price:,} ریال را ثبت کرد و منتظر تایید شماست.",
            "/panel/price-approvals",
        )
        return record

    _apply_price(record, product, discount)
    return record


@transaction.atomic
def review_price(record: OfficialPrice, by: User, approve: bool, note: str = "") -> OfficialPrice:
    """تایید یا رد نرخِ در انتظار، توسط اتاق اصناف/اداره صمت/استانداری/مدیر کل."""
    if record.status != OfficialPrice.Status.PENDING:
        raise ValidationError({"status": "این نرخ قبلا بررسی شده است."})
    if getattr(by, "role", None) not in PRICE_REVIEWER_ROLES:
        raise ValidationError({"detail": "شما مجاز به تایید نرخ نیستید."})
    if not approve and not note:
        raise ValidationError({"note": "برای رد نرخ، دلیل را بنویسید."})

    record.status = OfficialPrice.Status.APPROVED if approve else OfficialPrice.Status.REJECTED
    record.reviewed_by = by
    record.reviewed_at = timezone.now()
    record.review_note = note
    record.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])

    product = record.product
    union_users = User.objects.filter(role=Role.UNION, union=product.union)
    if approve:
        _apply_price(record, product, record.max_discount_percent)
        notify(union_users, f"نرخ «{product.name}» تایید شد",
               f"نرخ {record.price:,} ریال اعمال شد. {note}".strip(), "/panel/products")
    else:
        notify(union_users, f"نرخ «{product.name}» رد شد", note, "/panel/products")
    return record


def _apply_price(record: OfficialPrice, product: Product, discount: int) -> None:
    """اعمال نرخ تاییدشده روی کالا، قیمت فروشگاه‌ها، اعلان‌ها و هشدارها."""
    previous = product.current_price
    price = record.price
    changed = previous != price

    product.current_price = price
    product.max_discount_percent = discount
    if changed:
        product.price_changed_at = timezone.now()
    product.save(update_fields=["current_price", "max_discount_percent", "price_changed_at", "updated_at"])

    if changed:
        # قیمت اعلامی همه فروشگاه‌ها فورا برابر نرخ مصوب جدید می‌شود تا قیمت قدیمی
        # (که ممکن است خارج از بازه مجاز باشد) به مردم نمایش داده نشود. فروشگاه با
        # ورود به داشبورد می‌تواند دوباره تا سقف تخفیف مجاز، قیمت خود را کم کند.
        # confirmed_at عمدا دست‌نخورده می‌ماند تا کالا همچنان «در انتظار به‌روزرسانی»
        # علامت بخورد و مهلت ۲۴ ساعته برقرار باشد.
        StoreOffer.objects.filter(product=product).exclude(price=price).update(price=price, updated_at=timezone.now())

    if changed and previous:
        hours = settings.MARKET["UPDATE_GRACE_HOURS"]
        owners = User.objects.filter(stores__offers__product=product).distinct()
        notify(
            owners,
            f"تغییر نرخ «{product.name}»",
            f"نرخ جدید {price:,} ریال است و فعلا قیمت فروشگاه شما هم برابر همین نرخ شد. "
            f"ظرف {hours} ساعت وارد شوید و قیمت خود را تایید یا کم کنید؛ "
            "در غیر این صورت این کالا موقتا از فهرست فروشگاه شما حذف می‌شود.",
            "/panel/prices",
        )
        change = percent_change(previous, price)
        if change is not None and abs(change) >= settings.MARKET["ALERT_CHANGE_PERCENT"]:
            from apps.observatory.services import raise_official_price_alert

            raise_official_price_alert(product, previous, price, change)


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
