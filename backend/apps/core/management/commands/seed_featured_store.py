"""ساخت «فروشگاه ویژه» آزمایشی با ۸ قلم کالا و یک بسته پیشنهادی.

فروشگاه ویژه به هیچ اتحادیه‌ای وابسته نیست، کالاهایش بدون تایید صمت نمایش داده می‌شود و در دکمه
«طرح ویژه تخفیف» صفحه اصلی می‌آید. اجرای دوباره بی‌خطر است (کالاهای هم‌نام به‌روز می‌شوند).

اجرا:  python manage.py seed_featured_store --mobile 09xxxxxxxxx
  --mobile  شماره موبایل مالک/کارشناس فروشگاه (با همین شماره با کد پیامکی وارد پنل می‌شود)
  --password  اختیاری: رمز عبور مالک برای ورود با رمز
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import Role, User
from apps.core.management.commands.seed_product_images import SIZE, draw
from apps.core.utils import normalize_mobile
from apps.orgs.models import Store
from apps.shop.commerce import ShopBundle, ShopBundleItem
from apps.shop.models import ShopProduct

STORE_NAME = "فروشگاه ویژه ناظر ۷۲۴"

# (نام، برند، واحد، قیمت مصرف‌کننده، قیمت با تخفیف [تومان]، موجودی، سقف خرید هر کاربر)
PRODUCTS = [
    ("برنج پاکستانی دانه بلند (کیسه ۱۰ کیلویی)", "برند آزمایشی", "pack", 3_100_000, 2_750_000, 200, 2),
    ("روغن مایع آفتابگردان ۱٫۸ لیتری", "برند آزمایشی", "pack", 1_350_000, 1_150_000, 300, 3),
    ("شکر سفید ۱ کیلویی", "برند آزمایشی", "kg", 420_000, 360_000, 500, 5),
    ("گوشت منجمد گوساله", "برند آزمایشی", "kg", 1_650_000, 1_450_000, 100, 3),
    ("مرغ گرم همدان", "برند آزمایشی", "kg", 290_000, 255_000, 150, 4),
    ("سیب زمینی (بسته ۳ کیلویی)", "برند آزمایشی", "pack", 230_000, 190_000, 300, 3),
    ("ماکارونی ۵۰۰ گرمی", "برند آزمایشی", "pack", 120_000, 98_000, 400, 6),
    ("عدس ۹۰۰ گرمی", "برند آزمایشی", "pack", 380_000, 320_000, 250, 4),
]
# بسته پیشنهادی نمونه: (عنوان، توضیح، قیمت بسته [تومان]، [(نام کالا، تعداد)])
BUNDLE = ("بسته خانواده", "برنج، گوشت و مرغ برای یک هفته", 4_350_000, [
    ("برنج پاکستانی دانه بلند (کیسه ۱۰ کیلویی)", 1), ("گوشت منجمد گوساله", 1), ("مرغ گرم همدان", 2),
])


# شکل تصویر هر کالا: (شکل، رنگ پس‌زمینه، رنگ اصلی)؛ شکل‌های grains/meat/chicken/potato از seed_product_images
LOOK = {
    "برنج": ("grains", (245, 241, 232), (196, 164, 106)),
    "روغن": ("bottle", (252, 248, 228), (232, 178, 40)),
    "شکر": ("bag", (240, 245, 250), (120, 160, 205)),
    "گوشت": ("meat", (235, 242, 248), (150, 70, 80)),
    "مرغ": ("chicken", (250, 245, 232), (226, 196, 122)),
    "سیب": ("potato", (245, 240, 228), (198, 158, 92)),
    "ماکارونی": ("pack", (252, 240, 226), (226, 140, 50)),
    "عدس": ("grains", (246, 238, 230), (172, 98, 52)),
}


def make_image(name: str) -> bytes:
    shape, bg, fg = next((v for k, v in LOOK.items() if name.startswith(k)), ("box", (240, 243, 241), (15, 118, 110)))
    if shape in ("bottle", "bag", "pack"):
        im = Image.new("RGB", (SIZE, SIZE), bg)
        d = ImageDraw.Draw(im)
        dark = tuple(max(0, c - 45) for c in fg)
        light = tuple(min(255, c + 40) for c in fg)
        if shape == "bottle":     # بطری روغن
            d.rounded_rectangle([150, 120, 250, 330], radius=30, fill=fg)
            d.rounded_rectangle([180, 70, 220, 130], radius=10, fill=dark)
            d.rounded_rectangle([165, 190, 235, 270], radius=10, fill=(255, 253, 247))
            d.ellipse([185, 212, 215, 248], fill=dark)
        elif shape == "bag":      # کیسه شکر
            d.rounded_rectangle([105, 120, 295, 325], radius=16, fill=fg)
            d.polygon([(105, 120), (200, 85), (295, 120)], fill=light)
            d.rounded_rectangle([140, 185, 260, 265], radius=10, fill=(255, 253, 247))
            for i in range(3):
                d.rectangle([158, 202 + i * 20, 242, 208 + i * 20], fill=dark)
        else:                     # بسته ماکارونی
            d.rounded_rectangle([120, 90, 280, 320], radius=14, fill=fg)
            d.rounded_rectangle([140, 150, 260, 250], radius=10, fill=(255, 253, 247))
            for i in range(5):
                d.rounded_rectangle([152 + i * 20, 125, 160 + i * 20, 310], radius=3, fill=light)
    else:
        im = draw(shape, bg, fg)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


class Command(BaseCommand):
    help = "ساخت فروشگاه ویژه آزمایشی با ۸ کالا و یک بسته پیشنهادی"

    def add_arguments(self, parser):
        parser.add_argument("--mobile", required=True, help="موبایل مالک فروشگاه ویژه")
        parser.add_argument("--password", default="", help="رمز عبور مالک (اختیاری)")

    @transaction.atomic
    def handle(self, *args, **opts):
        mobile = normalize_mobile(opts["mobile"])
        store = Store.objects.filter(is_featured=True).first()
        if not store:
            owner = User.objects.filter(mobile=mobile).first()
            if owner and owner.role not in (Role.CITIZEN, Role.STORE):
                raise CommandError("این شماره متعلق به یک کاربر سازمانی است؛ شماره دیگری بدهید.")
            if owner and owner.stores.exists():
                raise CommandError("این شماره قبلا برای فروشگاه دیگری ثبت شده است.")
            owner = owner or User.objects.create_user(mobile)
            owner.role = Role.STORE
            if not owner.first_name:
                owner.first_name, owner.last_name = "کارشناس", "فروشگاه ویژه"
            if opts["password"]:
                owner.set_password(opts["password"])
            owner.save()
            store = Store.objects.create(
                owner=owner, name=STORE_NAME, address="همدان", phone=mobile, status=Store.Status.ACTIVE,
                is_featured=True, reviewed_at=timezone.now(), working_hours="همه روزه ۸ تا ۲۱",
            )
            self.stdout.write(f"فروشگاه ساخته شد: {store.name}")

        products = {}
        for i, (name, brand, unit, old, price, stock, limit) in enumerate(PRODUCTS, 1):
            p, _ = ShopProduct.objects.update_or_create(
                store=store, name=name,
                defaults={
                    "brand": brand, "unit": unit, "old_price": old * 10, "price": price * 10, "stock": stock,
                    "per_user_limit": limit, "order": i, "is_special": True, "is_active": True, "is_available": True,
                    "status": ShopProduct.Status.APPROVED, "reviewed_at": timezone.now(),
                },
            )
            products[name] = p
            if not p.image:
                p.image.save(f"featured-{p.pk}.jpg", ContentFile(make_image(name)), save=True)

        title, desc, price, comps = BUNDLE
        bundle, _ = ShopBundle.objects.update_or_create(
            store=store, title=title, defaults={"description": desc, "price": price * 10, "is_active": True, "order": 1}
        )
        bundle.items.all().delete()
        ShopBundleItem.objects.bulk_create(
            ShopBundleItem(bundle=bundle, product=products[n], quantity=q) for n, q in comps
        )
        self.stdout.write(self.style.SUCCESS(
            f"آماده شد: {len(PRODUCTS)} کالا و بسته «{title}» در «{store.name}» (مالک: {store.owner.mobile})"
        ))
