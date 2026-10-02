"""چند محصول نمونه برای فروشگاه اینترنتی چند فروشگاه، صرفا برای نمایش قابلیت.

اجرا: python manage.py seed_shop_demo
"""
import io
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw

from apps.orgs.models import Store
from apps.shop.models import ShopCategory, ShopProduct

# (نام محصول، دسته، قیمت تومان، قیمت قبل تخفیف یا None، واحد، برند، رنگ)
CATALOG = {
    "مرغ و ماهی": [
        ("فیله مرغ تازه", "لبنیات و پروتئین", 215_000, None, "kg", "", (236, 206, 160)),
        ("ماهی قزل‌آلا رنگین‌کمان", "لبنیات و پروتئین", 480_000, 520_000, "kg", "", (196, 148, 148)),
        ("بال و بازوی مرغ", "لبنیات و پروتئین", 178_000, None, "kg", "", (232, 198, 150)),
        ("ماهی سفید منجمد", "لبنیات و پروتئین", 395_000, None, "kg", "", (168, 186, 206)),
    ],
    "قصابان": [
        ("چرخ‌کرده مخلوط تازه", "لبنیات و پروتئین", 1_450_000, None, "kg", "", (186, 86, 86)),
        ("کباب کوبیده آماده", "لبنیات و پروتئین", 1_280_000, 1_390_000, "kg", "", (176, 96, 76)),
        ("جگر و دل و قلوه", "لبنیات و پروتئین", 890_000, None, "kg", "", (146, 72, 84)),
    ],
    "خوار و بار": [
        ("روغن آفتابگردان ۱.۸ لیتری", "خواربار و مواد غذایی", 268_000, 295_000, "piece", "بهار", (226, 196, 110)),
        ("چای کیسه‌ای ۱۰۰ عددی", "نوشیدنی", 198_000, None, "pack", "گلستان", (168, 124, 92)),
        ("ماکارونی ۷۰۰ گرمی", "خواربار و مواد غذایی", 42_000, None, "pack", "زر", (228, 198, 128)),
        ("رب گوجه‌فرنگی ۸۰۰ گرمی", "خواربار و مواد غذایی", 118_000, 132_000, "piece", "روژین", (182, 74, 62)),
        ("شوینده ظرفشویی ۳.۷۵ لیتری", "بهداشتی و شوینده", 215_000, None, "piece", "پریل", (120, 170, 186)),
        ("عسل طبیعی الوند ۹۰۰ گرمی", "خواربار و مواد غذایی", 680_000, None, "piece", "", (214, 166, 76)),
    ],
}


def thumb(color) -> bytes:
    """تصویر کوچک و سبک برای محصول نمونه."""
    im = Image.new("RGB", (400, 300), tuple(min(255, c + 28) for c in color))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([120, 70, 280, 240], radius=22, fill=color)
    d.rounded_rectangle([150, 110, 250, 200], radius=14, fill=tuple(max(0, c - 45) for c in color))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80, optimize=True)
    return buf.getvalue()


class Command(BaseCommand):
    help = "ساخت محصولات نمونه برای فروشگاه اینترنتی فروشگاه‌ها"

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(1405)
        cats = {c.name: c for c in ShopCategory.objects.all()}
        if not cats:
            self.stdout.write(self.style.ERROR("ابتدا دستور seed_locations را اجرا کنید (دسته‌ها ساخته نشده‌اند)."))
            return
        made = 0
        for union_key, items in CATALOG.items():
            stores = list(Store.objects.filter(union__name__contains=union_key, status=Store.Status.ACTIVE))
            if not stores:
                continue
            # هر محصول را به دو فروشگاه از همان اتحادیه می‌دهیم تا ویترین‌ها خالی نماند
            for i, (name, cat, price, old, unit, brand, color) in enumerate(items):
                for store in {stores[i % len(stores)], stores[(i + 1) % len(stores)]}:
                    if ShopProduct.objects.filter(store=store, name=name).exists():
                        continue
                    p = ShopProduct(
                        store=store, category=cats.get(cat), name=name, unit=unit, brand=brand,
                        price=price * 10, old_price=old * 10 if old else None, order=i,
                        description="نمونه نمایشی برای فروشگاه اینترنتی؛ از پنل فروشگاه قابل ویرایش است.",
                    )
                    p.image.save(f"demo-{store.pk}-{i}.jpg", ContentFile(thumb(color)), save=True)
                    made += 1
        self.stdout.write(self.style.SUCCESS(f"{made} محصول نمونه برای فروشگاه‌های اینترنتی ساخته شد."))
