"""داده پایه: فهرست ۲۴ قلم کالای اساسی مصرفی و نهاده‌های دامی (مطابق پیوست «توزیع ۱۴۰۵»)
و دسته‌بندی‌های اصلی. مقادیر سبد خانوار تخمینی است و از پنل قابل اصلاح است."""
from django.core.management.base import BaseCommand

from apps.market.models import Category
from apps.observatory.models import Commodity

G = Commodity.Group
# (نام، گروه، واحد، مقدار ماهانه سبد خانوار، وارداتی یارانه‌ای)
COMMODITIES = [
    ("گوشت گوسفندی", G.PROTEIN, "کیلوگرم", 1, False),
    ("گوشت گوساله", G.PROTEIN, "کیلوگرم", 1, False),
    ("گوشت مرغ", G.PROTEIN, "کیلوگرم", 5, False),
    ("تخم مرغ", G.PROTEIN, "کیلوگرم", 2, False),
    ("شیر", G.DAIRY, "لیتر", 12, False),
    ("ماست پاستوریزه یک کیلویی", G.DAIRY, "کیلوگرم", 6, False),
    ("پنیر پاستوریزه ۴۰۰ گرمی", G.DAIRY, "بسته", 4, False),
    ("کره پاستوریزه ۱۰۰ گرمی", G.DAIRY, "بسته", 4, False),
    ("روغن سرخ‌کردنی ۸۱۰ گرمی", G.OIL_SUGAR, "عدد", 3, False),
    ("برنج پاکستانی", G.GRAIN, "کیلوگرم", 8, False),
    ("چای خشک", G.OTHER, "کیلوگرم", 0.5, False),
    ("ماکارونی ۵۰۰ گرمی", G.GRAIN, "بسته", 4, False),
    ("رب گوجه‌فرنگی یک کیلویی", G.OTHER, "عدد", 1, False),
    ("شکر", G.OIL_SUGAR, "کیلوگرم", 3, False),
    ("لوبیا چیتی", G.GRAIN, "کیلوگرم", 1, False),
    ("عدس", G.GRAIN, "کیلوگرم", 1, False),
    ("گوجه‌فرنگی", G.PRODUCE, "کیلوگرم", 4, False),
    ("سیب‌زمینی", G.PRODUCE, "کیلوگرم", 5, False),
    ("پیاز", G.PRODUCE, "کیلوگرم", 4, False),
    ("پوشک بچه ۱۲ تایی", G.HYGIENE, "بسته", 0, False),
    ("دستمال کاغذی ۳۰۰ برگ", G.HYGIENE, "بسته", 2, False),
    ("شامپوی مو نیم لیتری", G.HYGIENE, "عدد", 1, False),
    ("مایع ظرفشویی یک لیتری", G.HYGIENE, "عدد", 1, False),
    ("پودر لباسشویی", G.HYGIENE, "کیلوگرم", 1, False),
    ("روغن خام", G.FEED, "کیلوگرم", 0, True),
    ("جو", G.FEED, "کیلوگرم", 0, True),
    ("ذرت", G.FEED, "کیلوگرم", 0, True),
    ("کنجاله", G.FEED, "کیلوگرم", 0, True),
]

CATEGORIES = [
    ("خواربار", "basket"), ("گوشت و پروتئین", "meat"), ("مرغ و ماهی", "fish"), ("لبنیات", "milk"),
    ("میوه و تره‌بار", "apple"), ("حبوبات و غلات", "grain"), ("بهداشتی و شوینده", "soap"), ("نان", "bread"),
]


class Command(BaseCommand):
    help = "ایجاد داده پایه (کالاهای اساسی و دسته‌بندی‌ها)"

    def handle(self, *args, **opts):
        for i, (name, group, unit, qty, subsidized) in enumerate(COMMODITIES):
            Commodity.objects.update_or_create(
                name=name,
                defaults={"group": group, "unit": unit, "order": i, "subsidized": subsidized},
            )
            Commodity.objects.filter(name=name, basket_monthly_qty=0).update(basket_monthly_qty=qty)
        for i, (name, icon) in enumerate(CATEGORIES):
            Category.objects.get_or_create(name=name, defaults={"icon": icon, "order": i})
        self.stdout.write(self.style.SUCCESS(f"{len(COMMODITIES)} کالای اساسی و {len(CATEGORIES)} دسته ثبت شد."))
