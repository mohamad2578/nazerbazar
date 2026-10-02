"""مختصات جغرافیایی فروشگاه‌های همدان + تصویر کالاهای اساسی + دسته‌های فروشگاه اینترنتی.

مختصات تقریبی و بر اساس نشانی اعلام‌شده هر فروشگاه در شهر همدان است؛ از پنل هر فروشگاه
(«مشخصات فروشگاه») یا از کارتابل اتحادیه قابل اصلاح دقیق روی نقشه است.

اجرا: python manage.py seed_locations
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.orgs.models import Store
from apps.shop.models import ShopCategory

# نام فروشگاه → (عرض، طول) بر اساس نشانی اعلام‌شده در همدان
COORDS = {
    # اتحادیه مرغ و ماهی
    "حمید بهروز": (34.79281, 48.50764),            # میدان فلسطین
    "فروشگاه مهدی مهدی‌نیا": (34.80342, 48.51857),  # میدان پروانه‌ها
    "فروشگاه نور محمدی": (34.78194, 48.49361),      # سیلو
    "حمید رضا جعفری": (34.81047, 48.53126),         # شهید زمانی
    "حمید کشوادی": (34.79935, 48.51402),            # سرگذر
    # اتحادیه قصابان
    "عبدالله محبوبیان": (34.80518, 48.50291),       # هنرستان
    "علی شیردل": (34.79887, 48.51358),              # سرگذر
    "عباس رجبی": (34.79492, 48.52073),              # خیابان باباطاهر
    "سعید اخوان": (34.78673, 48.52611),             # ششصد دستگاه
    # اتحادیه خوار و بار
    "حسین رضا آژدهاک": (34.79736, 48.51589),        # بازار حسین‌خانی
    "حسین علی عسگری": (34.77218, 48.47985),         # شهرک صنعتی بوعلی ۲
    "سامان بشتاله": (34.79781, 48.51523),           # بازار حسین‌خانی
    "احمد بیاتی": (34.79698, 48.51634),             # راسته حسین‌خانی
}

SHOP_CATEGORIES = [
    ("خواربار و مواد غذایی", "basket"),
    ("لبنیات و پروتئین", "milk"),
    ("میوه و سبزیجات", "apple"),
    ("نان و شیرینی", "bread"),
    ("نوشیدنی", "cup"),
    ("بهداشتی و شوینده", "soap"),
    ("لوازم خانه", "home"),
    ("سایر", "box"),
]


class Command(BaseCommand):
    help = "ثبت مختصات فروشگاه‌ها و ساخت دسته‌های فروشگاه اینترنتی"

    @transaction.atomic
    def handle(self, *args, **opts):
        updated = 0
        for name, (lat, lng) in COORDS.items():
            n = Store.objects.filter(name=name, lat__isnull=True).update(lat=lat, lng=lng)
            updated += n
        for i, (name, icon) in enumerate(SHOP_CATEGORIES):
            ShopCategory.objects.get_or_create(name=name, defaults={"icon": icon, "order": i})
        missing = Store.objects.filter(lat__isnull=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"مختصات {updated} فروشگاه ثبت شد ({missing} فروشگاه بدون مختصات باقی ماند). "
            f"{ShopCategory.objects.count()} دسته محصولات فروشگاهی آماده است."
        ))
