"""ساخت تصاویر اسپلش و آیکن اپلیکیشن اندروید ناظر ۷۲۴.

همه تصاویر از روی لوگوی سایت (frontend/public/icon.svg) بازسازی می‌شوند تا ظاهر اپ و سایت
یکی باشد. هر بار که طراحی عوض شد، همین را دوباره اجرا کنید:

    python scripts/make_assets.py

نیازمندی‌ها: Pillow، arabic-reshaper و python-bidi (برای چیدن درست متن فارسی).
"""
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android" / "app" / "src" / "main" / "res"
FONTS = ROOT.parent / "frontend" / "node_modules" / "vazirmatn" / "fonts" / "ttf"

BRAND = (15, 118, 110)        # #0f766e
BRAND_DARK = (10, 82, 77)     # برای گرادیان پایین صفحه
ACCENT = (251, 191, 36)       # #fbbf24
WHITE = (255, 255, 255)

SS = 4  # ابرنمونه‌برداری برای لبه‌های نرم


def fa(text: str) -> str:
    """چیدمان و اتصال درست حروف فارسی برای رسم با Pillow."""
    return get_display(arabic_reshaper.reshape(text))


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Vazirmatn-{weight}.ttf"), size)


def draw_mark(d: ImageDraw.ImageDraw, x: float, y: float, s: float, stroke=WHITE):
    """نمودار رو به بالا و نقطه زرد لوگو، در مختصات ۶۴×۶۴ آیکن اصلی."""
    k = s / 64
    pts = [(x + px * k, y + py * k) for px, py in [(18, 40), (27, 30), (34, 36), (46, 21)]]
    w = max(1, round(5 * k))
    d.line(pts, fill=stroke, width=w, joint="curve")
    r = w / 2
    for px, py in (pts[0], pts[-1]):
        d.ellipse((px - r, py - r, px + r, py + r), fill=stroke)
    cx, cy, cr = x + 46 * k, y + 21 * k, 4 * k
    d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=ACCENT)


def logo_tile(size: int, bg=BRAND, radius_ratio=14 / 64, inner=1.0) -> Image.Image:
    """کاشی گرد‌گوشه لوگو (همان icon.svg)."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * radius_ratio, fill=bg)
    m = big * (1 - inner) / 2
    draw_mark(d, m, m, big * inner)
    return img.resize((size, size), Image.LANCZOS)


def launcher_icons():
    sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    fg_sizes = {k: v * 108 // 48 for k, v in sizes.items()}
    for dens, px in sizes.items():
        folder = RES / f"mipmap-{dens}"
        logo_tile(px).save(folder / "ic_launcher.png")
        # آیکن گرد
        big = px * SS
        rnd = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(rnd)
        d.ellipse((0, 0, big - 1, big - 1), fill=BRAND)
        draw_mark(d, big * 0.08, big * 0.08, big * 0.84)
        rnd.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher_round.png")
        # لایه جلویی آیکن تطبیقی: فقط نشان، داخل ناحیه امن ۶۶٪ مرکزی
        fpx = fg_sizes[dens]
        fbig = fpx * SS
        fg = Image.new("RGBA", (fbig, fbig), (0, 0, 0, 0))
        draw_mark(ImageDraw.Draw(fg), fbig * 0.2, fbig * 0.2, fbig * 0.6)
        fg.resize((fpx, fpx), Image.LANCZOS).save(folder / "ic_launcher_foreground.png")
    (RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        '    <color name="ic_launcher_background">#0F766E</color>\n</resources>\n',
        encoding="utf-8",
    )


def splash(w: int, h: int) -> Image.Image:
    """صفحه اسپلش: گرادیان سبز سازمانی، لوگو با هاله نرم، نام و شعار اپ."""
    img = Image.new("RGB", (w, h), BRAND)
    # گرادیان عمودی ملایم
    grad = Image.new("RGB", (1, h))
    for yy in range(h):
        t = yy / max(1, h - 1)
        grad.putpixel((0, yy), tuple(round(a + (b - a) * t) for a, b in zip(BRAND, BRAND_DARK)))
    img.paste(grad.resize((w, h)))

    unit = min(w, h)
    tile = round(unit * 0.26)
    cx, cy = w // 2, round(h * 0.44) if h > w else round(h * 0.40)

    # هاله روشن پشت لوگو
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gr = tile * 0.95
    ImageDraw.Draw(glow).ellipse((cx - gr, cy - gr, cx + gr, cy + gr), fill=(255, 255, 255, 46))
    img.paste(glow.filter(ImageFilter.GaussianBlur(tile * 0.35)), (0, 0), glow.filter(ImageFilter.GaussianBlur(tile * 0.35)))

    # کاشی سفید با نشان سبز
    t = Image.new("RGBA", (tile * SS, tile * SS), (0, 0, 0, 0))
    td = ImageDraw.Draw(t)
    td.rounded_rectangle((0, 0, tile * SS - 1, tile * SS - 1), radius=tile * SS * 0.24, fill=WHITE)
    draw_mark(td, 0, 0, tile * SS, stroke=BRAND)
    t = t.resize((tile, tile), Image.LANCZOS)
    img.paste(t, (cx - tile // 2, cy - tile // 2), t)

    d = ImageDraw.Draw(img)
    title = font("Black", round(unit * 0.085))
    sub = font("Medium", round(unit * 0.036))
    foot = font("Regular", round(unit * 0.026))
    ty = cy + tile // 2 + round(unit * 0.07)
    d.text((cx, ty), fa("ناظر ۷۲۴"), font=title, fill=WHITE, anchor="mt")
    d.text((cx, ty + round(unit * 0.115)), fa("شفافیت قیمت کالاهای اساسی"), font=sub, fill=(220, 240, 237), anchor="mt")
    d.text((cx, h - round(unit * 0.07)), "nazer724.ir", font=foot, fill=(170, 214, 208), anchor="mb")
    return img


def splash_images():
    for png in RES.rglob("splash.png"):
        w, h = Image.open(png).size
        splash(w, h).save(png, optimize=True)
        print("splash", png.relative_to(RES), (w, h))


if __name__ == "__main__":
    launcher_icons()
    splash_images()
    print("done")
