from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.accounts.models import notify
from apps.core.utils import tracking_code
from apps.orgs.models import Store

from .models import Allocation, AllocationShare, Quota, QuotaEvent


def _assert_capacity(total, used, extra, label):
    if Decimal(used or 0) + Decimal(str(extra)) > Decimal(total):
        raise ValidationError({"quantity": f"مجموع {label} از مقدار کل ({total}) بیشتر می‌شود."})


@transaction.atomic
def set_share(allocation: Allocation, union, quantity) -> AllocationShare:
    if allocation.status == Allocation.Status.CLOSED:
        raise ValidationError({"allocation": "این تخصیص بسته شده است."})
    if union.chamber.county.province_id != allocation.province_id:
        raise ValidationError({"union": "اتحادیه باید در همان استان باشد."})
    assigned = Quota.objects.filter(share__allocation=allocation, share__union=union).exclude(
        status=Quota.Status.CANCELED
    ).aggregate(s=Sum("quantity"))["s"]
    if assigned and Decimal(str(quantity)) < assigned:
        raise ValidationError({"quantity": f"این اتحادیه تاکنون {assigned} را بین فروشگاه‌ها تقسیم کرده است."})
    others = allocation.shares.exclude(union=union).aggregate(s=Sum("quantity"))["s"]
    _assert_capacity(allocation.total_quantity, others, quantity, "سهم اتحادیه‌ها")
    share, _ = AllocationShare.objects.update_or_create(allocation=allocation, union=union, defaults={"quantity": quantity})
    return share


@transaction.atomic
def assign_quota(share: AllocationShare, store: Store, quantity, actor, carrier="") -> Quota:
    if share.allocation.status != Allocation.Status.ACTIVE:
        raise ValidationError({"allocation": "تخصیص باید در وضعیت «در حال توزیع» باشد."})
    if store.union_id != share.union_id or store.status != Store.Status.ACTIVE:
        raise ValidationError({"store": "فروشگاه باید فعال و عضو همین اتحادیه باشد."})
    used = share.quotas.exclude(status=Quota.Status.CANCELED).aggregate(s=Sum("quantity"))["s"]
    _assert_capacity(share.quantity, used, quantity, "سهمیه فروشگاه‌ها")
    q = Quota.objects.create(
        share=share, store=store, quantity=quantity, carrier=carrier, tracking_code=tracking_code("Q")
    )
    QuotaEvent.objects.create(quota=q, status=q.status, actor=actor, note=f"سهمیه {quantity} {share.allocation.unit}")
    notify(
        [store.owner], f"سهمیه جدید: {share.allocation.commodity.name}", f"کد رهگیری {q.tracking_code}", "/panel/quotas"
    )
    return q


def suggest_split(share: AllocationShare) -> list[dict]:
    """پیشنهاد تقسیم سهم اتحادیه بین فروشگاه‌های فعال.
    وزن هر فروشگاه = ۱ + امتیاز مشتریان/۵؛ فروشگاه خوش‌نام‌تر سهم بیشتری می‌گیرد."""
    stores = list(Store.objects.filter(union=share.union, status=Store.Status.ACTIVE))
    if not stores:
        return []
    weights = [1 + float(s.rating_avg or 0) / 5 for s in stores]
    total_w = sum(weights)
    return [
        {"store": s.pk, "store_name": s.name, "quantity": round(float(share.quantity) * w / total_w, 2)}
        for s, w in zip(stores, weights)
    ]


TRANSITIONS = {
    Quota.Status.ASSIGNED: {Quota.Status.DISPATCHED, Quota.Status.CANCELED},
    Quota.Status.DISPATCHED: {Quota.Status.RECEIVED, Quota.Status.CANCELED},
    Quota.Status.RECEIVED: {Quota.Status.RECEIVED, Quota.Status.SOLD_OUT},
}


@transaction.atomic
def advance_quota(q: Quota, status: str, actor, received_quantity=None, sold_quantity=None, note="") -> Quota:
    """RECEIVED -> RECEIVED یعنی گزارش فروش میانی بدون تغییر وضعیت."""
    if status not in TRANSITIONS.get(q.status, set()):
        raise ValidationError({"status": "تغییر وضعیت مجاز نیست."})
    if status == Quota.Status.RECEIVED and q.status != status:
        if received_quantity is None:
            raise ValidationError({"received_quantity": "مقدار تحویل‌شده را وارد کنید."})
        received = Decimal(str(received_quantity))
        if received > q.quantity:
            raise ValidationError({"received_quantity": "مقدار تحویلی بیشتر از سهمیه است."})
        q.received_quantity = received
        if received < q.quantity:
            note = f"{note} کسری تحویل: {q.quantity - received}".strip()
    if sold_quantity is not None:
        if Decimal(str(sold_quantity)) > Decimal(q.received_quantity or 0):
            raise ValidationError({"sold_quantity": "مقدار فروش بیشتر از مقدار تحویلی است."})
        q.sold_quantity = sold_quantity
    if status == Quota.Status.SOLD_OUT:
        q.sold_quantity = q.received_quantity or 0
    q.status = status
    q.save()
    QuotaEvent.objects.create(quota=q, status=status, actor=actor, note=note)
    return q
