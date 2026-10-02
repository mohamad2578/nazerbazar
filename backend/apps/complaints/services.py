from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User, notify
from apps.core.utils import tracking_code
from apps.orgs.models import Store

from .models import Complaint, ComplaintEvent

FINAL = {Complaint.Status.RESOLVED, Complaint.Status.REJECTED}


@transaction.atomic
def submit_complaint(reporter: User, data: dict) -> Complaint:
    store = data.get("store")
    product = data.get("product")
    chamber = data.pop("chamber", None)
    if store:
        if store.status != Store.Status.ACTIVE:
            raise ValidationError({"store": "فروشگاه انتخاب‌شده فعال نیست."})
        union = store.union
        chamber = union.chamber
        offer = store.offers.filter(product=product).first() if product else None
        data["announced_price"] = offer.price if offer else None
    else:
        if not chamber or not data.get("shop_name"):
            raise ValidationError({"store": "فروشگاه یا نام و شهرستان فروشنده را مشخص کنید."})
        union = product.union if product and product.union.chamber_id == chamber.pk else None
    if product:
        data["official_price"] = product.current_price
    c = Complaint.objects.create(
        reporter=reporter, union=union, chamber=chamber, tracking_code=tracking_code("C"), **data
    )
    ComplaintEvent.objects.create(complaint=c, actor=reporter, status=c.status, note="شکایت ثبت شد.")
    target = f"/panel/complaints/{c.pk}"
    if union:
        notify(User.objects.filter(role=Role.UNION, union=union), "شکایت جدید", f"کد {c.tracking_code}", target)
    notify(
        User.objects.filter(role=Role.CHAMBER, chamber=chamber),
        "رونوشت شکایت" if union else "شکایت جدید (فروشنده خارج از سامانه)",
        f"کد {c.tracking_code}",
        target,
    )
    return c


@transaction.atomic
def change_status(c: Complaint, actor: User, status: str, note="", violation=None, suspend_store=False, is_public=True):
    if c.status in FINAL and actor.role not in (Role.CHAMBER, Role.ADMIN, Role.GOVERNORATE):
        raise ValidationError({"status": "این شکایت بسته شده است."})
    if status not in Complaint.Status.values:
        raise ValidationError({"status": "وضعیت نامعتبر است."})
    if status in FINAL and not note:
        raise ValidationError({"note": "برای بستن شکایت، نتیجه رسیدگی را بنویسید."})
    c.status = status
    if violation is not None:
        c.violation_confirmed = violation
    if status in FINAL:
        c.resolution = note
        c.resolved_at = timezone.now()
    c.save()
    ComplaintEvent.objects.create(complaint=c, actor=actor, status=status, note=note, is_public=is_public)
    if suspend_store and c.store and violation:
        c.store.set_status(Store.Status.SUSPENDED, actor, f"تخلف محرز در شکایت {c.tracking_code}")
        notify([c.store.owner], "تعلیق فروشگاه", f"به دلیل تخلف در شکایت {c.tracking_code}", "/panel")
    notify([c.reporter], f"به‌روزرسانی شکایت {c.tracking_code}", c.get_status_display(), f"/track?code={c.tracking_code}")
    return c
