"""داده واقعی اولیه (درخواست کاربر، مهر ۱۴۰۵): فقط ۴ اتحادیه، ۶ کالا و فروشگاه‌های واقعی آن‌ها
تا سایت در ابتدای راه‌اندازی شلوغ نباشد. تمام داده‌های نمایشی/تستی قبلی (فروشگاه، کالا، قیمت،
شکایت، تخصیص) حذف می‌شود؛ ساختار سازمانی (استان/شهرستان/اتاق‌اصناف/اتحادیه) و کاربران ورود دست‌نخورده می‌ماند.

اجرا: python manage.py seed_curated
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User
from apps.complaints.models import Complaint, ComplaintEvent
from apps.distribution.models import Allocation, AllocationShare, Quota, QuotaEvent
from apps.market.models import DailySnapshot, OfferLog, OfficialPrice, Product, Review, StoreOffer
from apps.market.services import set_official_price, upsert_offer
from apps.observatory.models import Alert
from apps.orgs.models import Store, Union

PASSWORD = "demo12345"

# (نام کالا، واحد، نرخ مصوب به تومان)
PRODUCTS = {
    "خوار و بار": [("برنج", "kg", 180_000), ("تخم مرغ", "kg", 110_000)],
    "قصابان": [("گوشت قرمز", "kg", 1_800_000), ("گوشت قرمز منجمد", "kg", 1_200_000)],
    "مرغ و ماهی": [("مرغ گرم", "kg", 150_000)],
    "میوه و تره بار": [("سیب زمینی", "kg", 65_000)],
}

# (نام اتحادیه در کد، نام فروشگاه/مسئول، نشانی، موبایل یا None)
STORES = {
    "مرغ و ماهی": [
        ("حمید بهروز", "میدان فلسطین، جنب فروشگاه رفاه", None),
        ("فروشگاه مهدی مهدی‌نیا", "میدان پروانه‌ها", "09181500221"),
        ("فروشگاه نور محمدی", "سیلو، جنب فروشگاه شهر و روستا", None),
        ("حمید رضا جعفری", "انتهای شهید زمانی", "09188125848"),
        ("حمید کشوادی", "اول سرگذر", "09182053005"),
    ],
    "قصابان": [
        ("عبدالله محبوبیان", "هنرستان، کوچه سلیمانی", "09183110191"),
        ("علی شیردل", "سرگذر", "09183128336"),
        ("عباس رجبی", "خیابان باباطاهر، مقابل مسجد بهبهانی", None),
        ("سعید اخوان", "ششصد دستگاه، جنب مسجد مهدیه", "09181116160"),
    ],
    "خوار و بار": [
        ("حسین رضا آژدهاک", "بازار حسین‌خانی، کوچه ایزدی", "09188116360"),
        ("حسین علی عسگری", "شهرک صنعتی بوعلی ۲، بلوار پورسینا", "09188121724"),
        ("سامان بشتاله", "بازار حسین‌خانی، کوچه اصلیان، پلاک ۴۲", "09188111513"),
        ("احمد بیاتی", "راسته حسین‌خانی، سرای تجارت", "09183120045"),
    ],
}


def _placeholder_mobile(i: int) -> str:
    return f"0937000{i:04d}"


class Command(BaseCommand):
    help = "پاک‌سازی داده نمایشی و ساخت داده واقعی اولیه (۴ اتحادیه، ۶ کالا، فروشگاه‌های مشخص)"

    @transaction.atomic
    def handle(self, *args, **opts):
        # ── پاک‌سازی کامل داده تراکنشی قبلی ──────────────────────────────
        QuotaEvent.objects.all().delete()
        Quota.objects.all().delete()
        AllocationShare.objects.all().delete()
        Allocation.objects.all().delete()
        ComplaintEvent.objects.all().delete()
        Complaint.objects.all().delete()
        Review.objects.all().delete()
        OfferLog.objects.all().delete()
        StoreOffer.objects.all().delete()
        OfficialPrice.objects.all().delete()
        DailySnapshot.objects.all().delete()
        Alert.objects.all().delete()
        Product.objects.all().delete()
        store_owner_ids = list(Store.objects.values_list("owner_id", flat=True))
        Store.objects.all().delete()
        User.objects.filter(pk__in=store_owner_ids, role=Role.STORE).delete()

        # ── یکدست‌سازی اتحادیه‌ها: فقط ۴ اتحادیه‌ای که کاربر ورودشان را دارد ──
        keep = {"اتحادیه خواربار": "اتحادیه خوار و بار", "اتحادیه قصابان": None, "اتحادیه مرغ و ماهی": None}
        for old_name, new_name in keep.items():
            if new_name:
                Union.objects.filter(name=old_name).update(name=new_name)
        # اتحادیه میوه و تره‌بار: یکی نگه داشته می‌شود (همانی که کاربرش به آن وصل است)، بقیه حذف
        keep_fruit = Union.objects.filter(users__role=Role.UNION, users__mobile="09120000103").first()
        Union.objects.filter(name__icontains="میوه").exclude(pk=keep_fruit.pk).delete()
        Union.objects.filter(name__icontains="میوه").update(name="اتحادیه میوه و تره بار")
        # نسخه تکراری «خوار و بار» بدون پیشوند (باقی‌مانده از انتقال داده قدیمی)
        Union.objects.filter(name="خوار و بار").delete()

        unions = {u.name.replace("اتحادیه ", ""): u for u in Union.objects.all()}
        by_key = {
            "خوار و بار": unions["خوار و بار"],
            "قصابان": unions["قصابان"],
            "مرغ و ماهی": unions["مرغ و ماهی"],
            "میوه و تره بار": unions["میوه و تره بار"],
        }

        # ── کالاها و نرخ مصوب ─────────────────────────────────────────────
        products: dict[str, Product] = {}
        for key, items in PRODUCTS.items():
            union = by_key[key]
            union_user = User.objects.filter(role=Role.UNION, union=union).first()
            for name, unit, price_toman in items:
                p = Product.objects.create(union=union, name=name, unit=unit, unit_amount=1, is_active=True)
                set_official_price(p, price_toman * 10, union_user, note="نرخ اولیه")
                products[name] = p

        # ── فروشگاه‌ها ────────────────────────────────────────────────────
        i = 0
        for key, rows in STORES.items():
            union = by_key[key]
            for name, address, phone in rows:
                i += 1
                mobile = phone or _placeholder_mobile(i)
                owner, _ = User.objects.get_or_create(
                    mobile=mobile,
                    defaults={"role": Role.STORE, "first_name": name.split()[0], "last_name": " ".join(name.split()[1:])},
                )
                owner.set_password(PASSWORD)
                owner.save()
                store = Store.objects.create(
                    owner=owner, union=union, name=name, phone=phone or "",
                    address=f"همدان، {address}", status=Store.Status.ACTIVE,
                )

                if key == "مرغ و ماهی":
                    targets = [products["مرغ گرم"]]
                elif key == "قصابان":
                    targets = [products["گوشت قرمز"], products["گوشت قرمز منجمد"]]
                elif key == "خوار و بار":
                    targets = [products["برنج"], products["تخم مرغ"]]
                else:
                    targets = [products["سیب زمینی"]]

                for prod in targets:
                    price = random.randint(prod.min_allowed_price, prod.current_price)
                    # گرد کردن به نزدیک‌ترین ۱۰۰۰ ریال (۱۰۰ تومان) برای خوانایی
                    price = round(price / 1000) * 1000
                    price = max(prod.min_allowed_price, min(prod.current_price, price))
                    upsert_offer(store, prod, price, True)

        self.stdout.write(self.style.SUCCESS(
            f"{Union.objects.count()} اتحادیه، {Product.objects.count()} کالا، {Store.objects.count()} فروشگاه ساخته شد. "
            f"رمز همه فروشگاه‌ها: {PASSWORD}"
        ))
        self.stdout.write(self.style.SUCCESS(f"شناسه سیب‌زمینی برای لینک اسلاید: {products['سیب زمینی'].pk}"))
