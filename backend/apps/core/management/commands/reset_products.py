"""جایگزینی فهرست کالاهای اساسی هر اتحادیه با فهرست اعلام‌شده (مهر ۱۴۰۵).

کالاهای قبلی هر اتحادیه و قیمت‌های اعلامی فروشگاه‌ها روی آن‌ها حذف می‌شود و کالاهای
جدید با نرخ مصوب ثبت می‌گردد؛ سپس برای هر فروشگاه قیمتی تصادفی بین نرخ مصوب تا
حداکثر ۲۰٪ زیر آن ثبت می‌شود. فروشگاه‌ها، اتحادیه‌ها و کاربران دست‌نخورده می‌مانند.

اجرا: python manage.py reset_products
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User
from apps.market.models import DailySnapshot, OfferLog, OfficialPrice, Product, StoreOffer
from apps.market.services import set_official_price, upsert_offer
from apps.observatory.models import Alert
from apps.orgs.models import Store, Union

# نام اتحادیه (بدون پیشوند «اتحادیه») → [(نام کالا، واحد، نرخ مصوب به تومان)]
CATALOG: dict[str, list[tuple[str, str, int]]] = {
    "قصابان": [
        ("ران و سر دست گوسفند نر", "kg", 2_100_000),
        ("گوشت مخلوط گوسفندی نر", "kg", 1_650_000),
        ("ران و سر دست گوسفند ماده", "kg", 1_650_000),
        ("گوشت مخلوط گوسفندی ماده", "kg", 1_300_000),
        ("گوشت گاو و گوساله نرمه", "kg", 2_050_000),
    ],
    "مرغ و ماهی": [
        ("مرغ گرم شمال", "kg", 250_000),
        ("مرغ گرم همدان", "kg", 240_000),
        ("تخم مرغ شانه‌ای ۲ کیلویی", "pack", 530_000),
    ],
    "میوه و تره بار": [
        ("سیب زمینی ۳ کیلویی", "pack", 200_000),
    ],
    "خوار و بار": [
        ("برنج پاکستانی دانه بلند", "kg", 315_000),
        ("برنج پاکستانی دانه کوتاه", "kg", 280_000),
        ("برنج پاکستانی آر سیکس", "kg", 150_000),
        ("برنج هندی", "kg", 280_000),
        ("برنج تایلندی", "kg", 190_000),
    ],
}


class Command(BaseCommand):
    help = "حذف کالاهای فعلی اتحادیه‌ها و ثبت فهرست کالاهای اعلام‌شده به‌همراه قیمت فروشگاه‌ها"

    @transaction.atomic
    def handle(self, *args, **opts):
        unions = {u.name.replace("اتحادیه ", ""): u for u in Union.objects.all()}
        missing = [k for k in CATALOG if k not in unions]
        if missing:
            self.stderr.write(self.style.ERROR(f"این اتحادیه‌ها در سامانه نیستند: {missing}"))
            return

        targets = [unions[k] for k in CATALOG]
        old = Product.objects.filter(union__in=targets)

        # ── حذف کالاهای قبلی این اتحادیه‌ها و هر داده‌ای که به آن‌ها وابسته است ──
        OfferLog.objects.filter(offer__product__in=old).delete()
        StoreOffer.objects.filter(product__in=old).delete()
        DailySnapshot.objects.filter(product__in=old).delete()
        Alert.objects.filter(product__in=old).delete()
        OfficialPrice.objects.filter(product__in=old).delete()
        removed = old.count()
        old.delete()

        # ── ثبت کالاهای جدید با نرخ مصوب ──
        created = []
        for key, items in CATALOG.items():
            union = unions[key]
            # نرخ را از طرف کاربر اتحادیه ثبت نمی‌کنیم تا نیاز به تایید نداشته باشد؛
            # اداره صمت (یا در نبودش مدیر کل) ثبت‌کننده نرخ اولیه است.
            by = (User.objects.filter(role=Role.SAMT).first()
                  or User.objects.filter(role=Role.ADMIN).first())
            for name, unit, toman in items:
                p = Product.objects.create(union=union, name=name, unit=unit, unit_amount=1, is_active=True)
                set_official_price(p, toman * 10, by, note="نرخ اولیه")
                created.append(p)

        # ── قیمت اعلامی فروشگاه‌ها: تصادفی بین نرخ مصوب تا ۲۰٪ زیر آن ──
        offers = 0
        for store in Store.objects.filter(status=Store.Status.ACTIVE):
            allowed = store.priceable_union_ids()
            for p in created:
                if p.union_id not in allowed:
                    continue
                price = round(random.randint(p.min_allowed_price, p.current_price) / 1000) * 1000
                price = max(p.min_allowed_price, min(p.current_price, price))
                upsert_offer(store, p, price, True)
                offers += 1

        self.stdout.write(self.style.SUCCESS(
            f"{removed} کالای قبلی حذف و {len(created)} کالای جدید با {offers} قیمت اعلامی ثبت شد."
        ))
