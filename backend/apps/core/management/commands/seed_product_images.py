"""تصویر پیش‌فرض کوچک برای کالاهای اساسی نمونه.

تصویرها به‌صورت برنامه‌ای ساخته می‌شوند (۴۰۰×۴۰۰ و سبک) تا بدون نیاز به فایل خارجی،
کالاهای تستی تصویر داشته باشند. فروشگاه/اتحادیه بعدا می‌تواند تصویر واقعی را جایگزین کند.

اجرا: python manage.py seed_product_images [--force]
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from apps.market.models import Product

SIZE = 400

# نام کالا → (رنگ پس‌زمینه، رنگ اصلی، شکل)
STYLES = {
    "برنج": ((245, 241, 232), (196, 164, 106), "grains"),
    "تخم مرغ": ((247, 243, 233), (226, 183, 106), "eggs"),
    "گوشت قرمز": ((248, 236, 236), (178, 62, 62), "meat"),
    "گوشت قرمز منجمد": ((235, 242, 248), (132, 84, 96), "meat"),
    "مرغ گرم": ((250, 245, 232), (226, 196, 122), "chicken"),
    "سیب زمینی": ((245, 240, 228), (198, 158, 92), "potato"),
}
DEFAULT = ((240, 243, 241), (15, 118, 110), "box")


def _ellipse(d, box, fill, outline=None):
    d.ellipse(box, fill=fill, outline=outline, width=4)


def draw(shape: str, bg, fg) -> Image.Image:
    im = Image.new("RGB", (SIZE, SIZE), bg)
    d = ImageDraw.Draw(im)
    dark = tuple(max(0, c - 40) for c in fg)
    light = tuple(min(255, c + 35) for c in fg)
    cx = SIZE // 2

    if shape == "grains":  # کیسه برنج
        d.rounded_rectangle([110, 130, 290, 330], radius=18, fill=fg)
        d.polygon([(110, 130), (200, 95), (290, 130)], fill=light)
        d.rounded_rectangle([145, 180, 255, 270], radius=10, fill=(255, 253, 247))
        for i in range(5):
            for j in range(4):
                x, y = 160 + i * 20, 198 + j * 20
                d.ellipse([x, y, x + 11, y + 15], fill=dark)
    elif shape == "eggs":  # شانه تخم‌مرغ
        d.rounded_rectangle([70, 150, 330, 300], radius=16, fill=(214, 198, 170))
        for i in range(3):
            for j in range(2):
                x, y = 100 + i * 80, 175 + j * 70
                _ellipse(d, [x, y, x + 60, y + 72], fg)
                _ellipse(d, [x + 14, y + 12, x + 34, y + 36], light)
    elif shape == "meat":  # برش گوشت
        d.rounded_rectangle([90, 120, 310, 300], radius=60, fill=fg)
        d.rounded_rectangle([130, 155, 270, 265], radius=45, fill=light)
        d.arc([150, 175, 250, 250], 200, 340, fill=dark, width=12)
        d.rounded_rectangle([92, 250, 308, 300], radius=40, fill=(250, 246, 240))
    elif shape == "chicken":  # مرغ
        _ellipse(d, [100, 150, 300, 310], fg)
        _ellipse(d, [230, 105, 310, 185], fg)
        d.polygon([(300, 135), (340, 148), (300, 162)], fill=(224, 136, 60))
        _ellipse(d, [272, 128, 286, 142], (60, 48, 42))
        d.arc([130, 200, 270, 300], 20, 160, fill=dark, width=10)
    elif shape == "potato":  # سیب‌زمینی
        for box in ([90, 170, 230, 280], [185, 140, 315, 250], [150, 240, 280, 330]):
            _ellipse(d, box, fg)
            d.ellipse([box[0] + 30, box[1] + 28, box[0] + 42, box[1] + 40], fill=dark)
            d.ellipse([box[0] + 70, box[1] + 55, box[0] + 80, box[1] + 65], fill=dark)
    else:  # جعبه عمومی
        d.rounded_rectangle([110, 140, 290, 310], radius=16, fill=fg)
        d.line([110, 200, 290, 200], fill=light, width=10)
        d.line([cx, 140, cx, 310], fill=light, width=10)
    return im


class Command(BaseCommand):
    help = "ساخت تصویر پیش‌فرض برای کالاهای اساسی بدون تصویر"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="تصویر کالاهایی که تصویر دارند هم بازنویسی شود")

    def handle(self, *args, **opts):
        qs = Product.objects.all() if opts["force"] else Product.objects.filter(image="")
        n = 0
        for p in qs:
            bg, fg, shape = STYLES.get(p.name, DEFAULT)
            buf = io.BytesIO()
            draw(shape, bg, fg).save(buf, format="JPEG", quality=82, optimize=True)
            p.image.save(f"product-{p.pk}.jpg", ContentFile(buf.getvalue()), save=True)
            n += 1
        self.stdout.write(self.style.SUCCESS(f"برای {n} کالا تصویر ساخته شد."))
