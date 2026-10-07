"""جایگزینی کامل فهرست فروشگاه‌ها با فهرست واقعی اعلام‌شده (مهر ۱۴۰۵).

کالاها، نرخ‌های مصوب، اتحادیه‌ها و کاربران سازمانی دست‌نخورده می‌مانند؛ فقط فروشگاه‌های
قبلی و داده وابسته‌شان (قیمت اعلامی، نظر، سفارش، سهمیه، شکایت) حذف و فروشگاه‌های جدید
با قیمت تصادفی بین «نرخ مصوب» و «۲۰٪ زیر نرخ مصوب» ساخته می‌شود.

مختصات نقشه تقریبی و بر پایه نشانی اعلام‌شده هر فروشگاه است و از پنل قابل اصلاح است.

اجرا: python manage.py reset_stores
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User
from apps.complaints.models import Complaint, ComplaintEvent
from apps.distribution.models import Quota, QuotaEvent
from apps.market.models import OfferLog, Review, StoreOffer
from apps.market.services import upsert_offer
from apps.observatory.models import Alert
from apps.orgs.models import Store, Union
from apps.shop.models import ShopProduct
from apps.shop.orders import Order, OrderEvent, OrderItem

PASSWORD = "demo12345"

# (نام فروشگاه/مسئول، موبایل، نشانی، عرض، طول) — مختصات تقریبی بر پایه نشانی در همدان
STORES: dict[str, list[tuple[str, str, str, float, float]]] = {
    "خوار و بار": [
        ("محمد حسین بابایی", "09187133203", "شهرک الوند", 34.77360, 48.48470),
        ("روح الله کریمی معتقد", "09182079151", "حصار امام", 34.82300, 48.54200),
        ("محمد گرجی (طبیعت)", "09188185501", "میدان شاهد", 34.78460, 48.49840),
        ("علی خدایی", "09185001607", "شهرک بهشتی", 34.76980, 48.52700),
        ("سید جواد سید شکری", "09189060914", "خضر", 34.80830, 48.53270),
        ("حکمعلی نقی پور", "09188114936", "شهرک فرهنگیان", 34.81480, 48.49300),
        ("آرش خدامرادی", "09184423575", "سیلو", 34.78194, 48.49361),
        ("رامین امینی نیک (مون مارکت)", "09353665098", "دارای پنج شعبه در سطح شهر", 34.79920, 48.51460),
    ],
    "قصابان": [
        ("علی باشماغی", "09183178698", "خیابان خضریان", 34.80600, 48.52900),
        ("علیرضا سپهری وفا", "09184474173", "خیابان شهدا، جنب پاساژ کوثر", 34.79680, 48.52140),
        ("امید نوروزی", "09184111351", "شهرک الوند، ۲۸ متری گلزار", 34.77210, 48.48210),
        ("شریفی نیا", "09183181360", "شهرک معلم، فلکه معلم", 34.78890, 48.47600),
        ("هاشم باشماغی", "09188181976", "دیزج، ایستگاه دوم", 34.82680, 48.55880),
        ("فرهاد پور مرادی", "09181116266", "خیابان شهدا، مقابل مسجد حاج خداکرم", 34.79750, 48.52350),
        ("سعید اخوان", "09121691090", "ششصد دستگاه، بازار روز", 34.78673, 48.52611),
    ],
    "میوه و تره بار": [
        ("علیرضا مرادی", "09183188285", "شهرک فرهنگیان، کوچه ریحان ۱۲", 34.81550, 48.49180),
        ("محمد تکرلی", "09377545778", "شهرک مدنی، خیابان فردیس، کوچه سرو ۴", 34.82200, 48.48350),
        ("رسول اقبالی", "09355760641", "شهرک الوند، کوچه لاله ۴", 34.77430, 48.48600),
        ("جلال معظمی", "09188082420", "بلوار بعثت، کوچه نستوه، پلاک ۱۷۱", 34.78550, 48.50750),
        ("احمد خلیلی سعید", "09189093735", "سرگذر، راسته کاه‌فروش‌ها، پلاک ۱۹", 34.79887, 48.51358),
        ("جعفر منوچهری", "09187130029", "میدان مدرس، بلوار شاه‌حسینی، پلاک ۱۲۲", 34.78400, 48.53160),
    ],
    "مرغ و ماهی": [
        ("ریحانه سلیمانی مغز", "09011176787", "جولان، فروشگاه شهروند", 34.80230, 48.50750),
        ("محمد احمدی همت", "09185022498", "بلوار مطهری، تپه حاج عنایت، کوچه رودخانه", 34.81120, 48.52150),
        ("مهدی امینی بشیر", "09185443826", "کوی جنت، خیابان شهید احمدی‌نسب، کوچه درنا", 34.80600, 48.49600),
        ("مهدی مهدی نیا", "09181500221", "انتهای خیابان شهدا", 34.79400, 48.52650),
        ("منوچهر نوروزی", "09183110921", "بلوار چمران، خیابان آرام شرقی", 34.78930, 48.48780),
        ("احمد صاحب چراغیان", "09183165634", "بلوار شهیدان بهادربیگی، پلاک ۹۳", 34.80980, 48.54100),
        ("احسان الماسی نیا", "09181118303", "حصار امام خمینی، پلاک ۳۳۴", 34.82350, 48.54320),
        ("بهزاد هاشمی", "09183158575", "کوی خضر، کوچه یاسمن", 34.80900, 48.53420),
        ("فاطمه مرادی", "09193246514", "قاسم آباد، کوچه سلامت ۱۵", 34.82900, 48.50700),
    ],
}


class Command(BaseCommand):
    help = "حذف فروشگاه‌های فعلی و ثبت فهرست واقعی فروشگاه‌ها (کالاها و نرخ مصوب حفظ می‌شود)"

    @transaction.atomic
    def handle(self, *args, **opts):
        # ── حذف فروشگاه‌های قبلی و هر داده‌ای که به آن‌ها وابسته است ──────────
        OrderEvent.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        ShopProduct.objects.all().delete()
        QuotaEvent.objects.all().delete()
        Quota.objects.all().delete()
        ComplaintEvent.objects.all().delete()
        Complaint.objects.all().delete()
        Alert.objects.filter(store__isnull=False).delete()
        Review.objects.all().delete()
        OfferLog.objects.all().delete()
        StoreOffer.objects.all().delete()
        owner_ids = list(Store.objects.values_list("owner_id", flat=True))
        removed = Store.objects.count()
        Store.objects.all().delete()
        User.objects.filter(pk__in=owner_ids, role=Role.STORE).delete()

        unions = {u.name.replace("اتحادیه ", ""): u for u in Union.objects.all()}

        # ── ثبت فروشگاه‌های جدید ─────────────────────────────────────────────
        offers = 0
        for key, rows in STORES.items():
            union = unions[key]
            # کالاهای همان اتحادیه که نرخ مصوب دارند
            targets = [p for p in union.products.filter(is_active=True) if p.current_price]
            for name, mobile, address, lat, lng in rows:
                person = name.split(" (")[0].split()
                owner, _ = User.objects.get_or_create(
                    mobile=mobile,
                    defaults={"first_name": person[0], "last_name": " ".join(person[1:])},
                )
                owner.role = Role.STORE
                owner.set_password(PASSWORD)
                owner.save()
                store = Store.objects.create(
                    owner=owner, union=union, name=name, phone=mobile,
                    address=f"همدان، {address}", lat=lat, lng=lng,
                    status=Store.Status.ACTIVE,
                )
                for prod in targets:
                    # قیمت تصادفی بین نرخ مصوب و حداکثر ۲۰٪ زیر آن، گرد به ۱۰۰ تومان
                    price = round(random.randint(prod.min_allowed_price, prod.current_price) / 1000) * 1000
                    price = max(prod.min_allowed_price, min(prod.current_price, price))
                    upsert_offer(store, prod, price, True)
                    offers += 1

        self.stdout.write(self.style.SUCCESS(
            f"{removed} فروشگاه قبلی حذف شد؛ {Store.objects.count()} فروشگاه جدید با {offers} قیمت اعلامی ثبت شد. "
            f"رمز ورود همه فروشگاه‌ها: {PASSWORD}"
        ))
