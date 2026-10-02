"""داده نمایشی برای آزمایش همه نقش‌ها. فقط روی محیط توسعه/آزمایشی اجرا شود.

کاربران (ورود با رمز demo12345 یا کد پیامکی):
  09120000000 مدیر کل | 09120000001 استانداری | 09120000002 اتاق اصناف
  0912000010x اتحادیه‌ها | 0912000020x فروشگاه‌ها | 09120000300 شهروند
"""
import random
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.complaints.models import Complaint
from apps.complaints.services import change_status, submit_complaint
from apps.distribution.models import Allocation, Quota
from apps.distribution.services import advance_quota, assign_quota, set_share
from apps.market.models import Category, DailySnapshot, Product, Review, StoreOffer
from apps.market.services import set_official_price, take_daily_snapshot, upsert_offer
from apps.observatory.models import Commodity, CommodityReport
from apps.observatory.services import scan_alerts
from apps.orgs.models import Chamber, County, Province, Store, Union

PASSWORD = "demo12345"
CENTER = (34.7983, 48.5148)  # همدان
STORE_NAMES = [
    "فروشگاه امید", "سوپرمارکت بهاران", "هایپر نگین", "فروشگاه سعید", "خواربار ولیعصر", "قصابی حاج رضا",
    "مرغ و ماهی دریا", "میوه‌فروشی باغ سبز", "فروشگاه آفتاب", "سوپر پارسا", "تره‌بار الوند", "فروشگاه کوهسار",
]
DEMO_PRODUCTS = {
    "خوار": [("برنج پاکستانی ۱۰ کیلویی", 23_000_000, "برنج پاکستانی", "pack", 10), ("شکر یک کیلو", 1_050_000, "شکر", "kg", 1),
             ("روغن سرخ‌کردنی ۸۱۰ گرمی", 1_450_000, "روغن سرخ‌کردنی ۸۱۰ گرمی", "piece", 1),
             ("لوبیا چیتی ایرانی", 4_200_000, "لوبیا چیتی", "kg", 1), ("عدس درشت", 3_100_000, "عدس", "kg", 1),
             ("ماکارونی ۵۰۰ گرمی", 520_000, "ماکارونی ۵۰۰ گرمی", "pack", 1), ("چای خشک ایرانی", 9_500_000, "چای خشک", "kg", 1)],
    "قصاب": [("گوشت گوسفندی مخلوط", 15_000_000, "گوشت گوسفندی", "kg", 1), ("گوشت گوساله", 14_500_000, "گوشت گوساله", "kg", 1)],
    "مرغ": [("مرغ گرم", 2_300_000, "گوشت مرغ", "kg", 1), ("تخم مرغ شانه‌ای", 1_900_000, "تخم مرغ", "kg", 1)],
    "میوه": [("گوجه‌فرنگی", 450_000, "گوجه‌فرنگی", "kg", 1), ("سیب‌زمینی", 380_000, "سیب‌زمینی", "kg", 1),
             ("پیاز زرد", 300_000, "پیاز", "kg", 1)],
}


def user(mobile, role, **kw):
    u, _ = User.objects.get_or_create(mobile=mobile, defaults={"role": role, **kw})
    for k, v in {"role": role, **kw}.items():
        setattr(u, k, v)
    u.set_password(PASSWORD)
    u.save()
    return u


class Command(BaseCommand):
    help = "ایجاد داده نمایشی"

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(1405)
        call_command("seed_base")
        admin = user("09120000000", Role.ADMIN, first_name="مدیر", last_name="سامانه", is_staff=True, is_superuser=True)

        prov, _ = Province.objects.get_or_create(name="همدان", defaults={"lat": CENTER[0], "lng": CENTER[1]})
        county, _ = County.objects.get_or_create(
            province=prov, name="همدان", defaults={"lat": CENTER[0], "lng": CENTER[1], "population": 780000}
        )
        for name, pop in [("ملایر", 300000), ("نهاوند", 180000), ("تویسرکان", 100000), ("اسدآباد", 105000)]:
            County.objects.get_or_create(province=prov, name=name, defaults={"population": pop})
        chamber = Chamber.objects.filter(county=county).first() or Chamber.objects.create(county=county, name="اتاق اصناف همدان")
        user("09120000001", Role.GOVERNORATE, province=prov, first_name="کارشناس", last_name="استانداری")
        user("09120000002", Role.CHAMBER, chamber=chamber, first_name="کارشناس", last_name="اتاق اصناف")

        unions = []
        for i, (key, title) in enumerate([("خوار", "اتحادیه خواربار"), ("قصاب", "اتحادیه قصابان"),
                                          ("مرغ", "اتحادیه مرغ و ماهی"), ("میوه", "اتحادیه میوه و تره‌بار")]):
            u = Union.objects.filter(chamber=chamber, name__contains=key).first() or Union.objects.create(chamber=chamber, name=title)
            unions.append((key, u))
            user(f"0912000010{i}", Role.UNION, union=u, first_name="مسئول", last_name=u.name)

        cats = {c.name: c for c in Category.objects.all()}
        cat_by_key = {"خوار": "خواربار", "قصاب": "گوشت و پروتئین", "مرغ": "مرغ و ماهی", "میوه": "میوه و تره‌بار"}
        commodities = {c.name: c for c in Commodity.objects.all()}
        for key, u in unions:
            union_user = User.objects.get(union=u, role=Role.UNION)
            for name, price, com, unit, amount in DEMO_PRODUCTS[key]:
                p, created = Product.objects.get_or_create(
                    union=u, name=name,
                    defaults={"unit": unit, "unit_amount": amount, "category": cats.get(cat_by_key[key]),
                              "commodity": commodities.get(com)},
                )
                if created or not p.current_price:
                    set_official_price(p, price, union_user)

        # فروشگاه‌ها
        stores = []
        for i, name in enumerate(STORE_NAMES):
            key, u = unions[0] if i < 6 else unions[1 + (i - 6) % 3] if i < 9 else unions[3]
            if name.startswith("قصابی"):
                key, u = unions[1]
            owner = user(f"091200002{i:02d}", Role.STORE, first_name="مالک", last_name=name.split()[-1])
            s, _ = Store.objects.get_or_create(owner=owner, defaults={
                "union": u, "name": name, "address": f"همدان، خیابان {random.choice(['بوعلی', 'شریعتی', 'اکباتان', 'تختی', 'مهدیه'])}، پلاک {i + 10}",
                "phone": f"08138{random.randint(100000, 999999)}", "license_no": f"18-{random.randint(10000, 99999)}",
                "lat": round(CENTER[0] + random.uniform(-0.03, 0.03), 6), "lng": round(CENTER[1] + random.uniform(-0.04, 0.04), 6),
                "working_hours": "۸ تا ۲۲",
            })
            s.status = Store.Status.PENDING if i == len(STORE_NAMES) - 1 else Store.Status.ACTIVE
            s.is_verified = i % 3 == 0
            s.save()
            stores.append(s)

        for s in stores:
            if s.status != Store.Status.ACTIVE:
                continue
            for p in Product.objects.filter(union=s.union):
                price = p.current_price - random.randint(0, p.max_discount_percent) * p.current_price // 100
                upsert_offer(s, p, max(price, p.min_allowed_price))

        citizen = user("09120000300", Role.CITIZEN, first_name="علی", last_name="رضایی")
        for s in stores[:8]:
            Review.objects.update_or_create(store=s, user=citizen, defaults={"rating": random.randint(3, 5), "comment": "برخورد مناسب و قیمت منصفانه"})
            s.rating_avg, s.rating_count = s.reviews.first().rating, 1
            s.save(update_fields=["rating_avg", "rating_count"])

        # شکایات نمونه
        if not Complaint.objects.exists():
            for i, s in enumerate(stores[:5]):
                p = Product.objects.filter(union=s.union).first()
                c = submit_complaint(citizen, {
                    "store": s, "product": p, "kind": Complaint.Kind.OVERPRICE, "reporter_name": citizen.full_name,
                    "paid_price": p.current_price + 150_000, "description": "قیمت دریافتی از نرخ اعلام‌شده بیشتر بود.",
                })
                if i < 2:
                    ux = User.objects.get(union=s.union, role=Role.UNION)
                    change_status(c, ux, Complaint.Status.REVIEWING, "بازرس اعزام شد.")
                    if i == 0:
                        change_status(c, ux, Complaint.Status.RESOLVED, "تخلف محرز شد و تذکر کتبی داده شد.", violation=True)

        # تاریخچه قیمت ۴۵ روز گذشته برای نمودارها
        today = timezone.localdate()
        take_daily_snapshot(today)
        base = list(DailySnapshot.objects.filter(date=today))
        for back in range(45, 0, -1):
            d = today - timedelta(days=back)
            factor = 1 - back * 0.0035 + random.uniform(-0.01, 0.01)
            for s in base:
                DailySnapshot.objects.update_or_create(date=d, product=s.product, county=s.county, defaults={
                    "official_price": int(s.official_price * factor),
                    "min_price": int(s.min_price * factor) if s.min_price else None,
                    "avg_price": int(s.avg_price * (factor + random.uniform(-0.01, 0.01))) if s.avg_price else None,
                    "max_price": int(s.max_price * factor) if s.max_price else None,
                    "offer_count": s.offer_count,
                })

        # یک تغییر نرخ اخیر تا قانون ۲۴ ساعته دیده شود
        rice = Product.objects.filter(name__startswith="برنج پاکستانی ۱۰").first()
        if rice:
            set_official_price(rice, int(rice.current_price * 1.08), User.objects.get(union=rice.union, role=Role.UNION), note="افزایش نرخ واردات")
            rice.refresh_from_db()
            offers = list(rice.offers.select_related("store"))
            for o in offers[1:]:
                upsert_offer(o.store, rice, rice.current_price - random.randint(0, 10) * rice.current_price // 100)
            # نرخ ۲۶ ساعت پیش تغییر کرده و فروشگاه اول به‌روز نکرده ← موقتا از فهرست عمومی حذف می‌شود
            now = timezone.now()
            Product.objects.filter(pk=rice.pk).update(price_changed_at=now - timedelta(hours=26))
            if offers:
                StoreOffer.objects.filter(pk=offers[0].pk).update(confirmed_at=now - timedelta(hours=30))

        # گزارش رصدخانه (نمونه جدول الف/ب پیوست)
        sheep = commodities["گوشت گوسفندی"]
        CommodityReport.objects.update_or_create(commodity=sheep, province=None, period=today, defaults={
            "annual_need_kt": 1160, "annual_production_kt": 960, "imports_kt": 150, "import_price": 8_079_800,
            "clearance_cost": 78_300, "neighbor_price_usd": 15, "per_capita_stat": 12,
            "producer_price": 7_000_000, "wholesale_price": 10_500_000, "consumer_price_county": 12_000_000,
            "consumer_price_center": 12_500_000, "consumer_price_tehran": 18_500_000, "national_min": 10_500_000,
            "national_max": 18_000_000, "national_avg": 15_500_000, "source": "پیوست توزیع ۱۴۰۵ — هفته سوم اردیبهشت",
        })

        # توزیع: تخصیص برنج یارانه‌ای
        if not Allocation.objects.exists():
            gov = User.objects.get(mobile="09120000001")
            a = Allocation.objects.create(
                province=prov, commodity=commodities["برنج پاکستانی"], title="توزیع برنج تنظیم بازار — مهر ۱۴۰۵",
                supplier="شرکت بازرگانی دولتی", total_quantity=20000, allocation_price=1_400_000, consumer_price=1_750_000,
                starts_on=today - timedelta(days=5), status=Allocation.Status.ACTIVE, created_by=gov,
            )
            share = set_share(a, unions[0][1], 8000)
            ux = User.objects.get(union=unions[0][1], role=Role.UNION)
            for j, s in enumerate([s for s in stores if s.union_id == unions[0][1].pk and s.status == "active"][:4]):
                q = assign_quota(share, s, 1500, ux, carrier="پخش البرز")
                advance_quota(q, Quota.Status.DISPATCHED, ux)
                if j < 3:
                    advance_quota(q, Quota.Status.RECEIVED, s.owner, received_quantity=1500 if j else 1350)
                    advance_quota(q, Quota.Status.RECEIVED, s.owner, sold_quantity=400 * (j + 1))

        take_daily_snapshot(today)
        scan_alerts(today)
        self.stdout.write(self.style.SUCCESS(f"داده نمایشی ایجاد شد. رمز همه کاربران: {PASSWORD} (مدیر: {admin.mobile})"))
