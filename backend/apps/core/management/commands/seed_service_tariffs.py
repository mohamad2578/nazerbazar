"""ثبت نرخ‌نامه خدمات «تعویض روغن» ۱۴۰۵ برای اتحادیه تعمیرکاران اتومبیل.

کالای خدماتی «تعویض روغن» زیر اتحادیه ساخته (یا به‌روز) می‌شود و ردیف‌های نرخ‌نامه با فهرست
زیر جایگزین می‌گردد. اجرای دوباره بی‌خطر است. کالاها و قیمت‌های دیگر دست‌نخورده می‌مانند.

اجرا:  python manage.py seed_service_tariffs
اگر نام اتحادیه در سامانه فرق دارد:  python manage.py seed_service_tariffs --union "بخشی از نام اتحادیه"
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.market.models import Product, ServiceTariff, Unit
from apps.orgs.models import Union

PRODUCT_NAME = "تعویض روغن"

# (شرح خدمت، تعرفه به ریال) — به ترتیب ردیف نرخ‌نامه
TARIFFS: list[tuple[str, int]] = [
    ("تعویض روغن انواع سواری و وانت", 800_000),
    ("تعویض روغن خودروهای خارجی و شاسی", 1_300_000),
    ("تعویض روغن خودروهای لوکس که می‌بایست سینی باز و بست کرد", 1_800_000),
    ("تعویض فیلتر روغن انواع سواری و وانت", 500_000),
    ("تعویض فیلتر روغن پژو ۲۰۶، زانتیا و شاسی", 800_000),
    ("تعویض صافی بنزین انواع سواری", 200_000),
    ("تعویض واسکازین گیربکس و دیفرانسیل انواع سواری و وانت دو طرف", 800_000),
    ("بازدید جعبه فرمان و گیربکس و دیفرانسیل انواع سواری و وانت دو طرف", 300_000),
    ("گریس کاری انواع سواری و وانت هر گریس خور با مبلغ گریس", 400_000),
    ("تعویض روغن مینی بوس و خاور تا بنز ده تن", 1_000_000),
    ("تعویض فیلتر روغن نیسان، مینی بوس و خاور تا بنز ده تن", 1_000_000),
    ("شستشوی کامل هواکش مینی بوس تا بنز ده تن", 1_200_000),
    ("گریس کاری مینی بوس، خاور، کامیون هر گریس خور با گریس", 500_000),
    ("تعویض واسکازین گیربکس و دیفرانسیل مینی بوس و خاور تا ۵ تن هر کدام", 1_600_000),
    ("بازدید گیربکس و دیفرانسیل مینی بوس، خاور ۵ تن هر کدام", 600_000),
    ("تعویض واسکازین گیربکس و دیفرانسیل ۵ تن به بالا", 2_000_000),
    ("تعویض فیلتر هوای کابین انواع سواری خارجی", 800_000),
    ("تعویض فیلتر هوای کابین انواع سواری ایرانی", 300_000),
    ("تعویض فیلتر بنزین انواع سواری خارجی توباکی", 5_000_000),
    ("تعویض فیلتر بنزین انواع سواری ایرانی", 800_000),
    ("تعویض روغن هیدرولیک فرمان کلیه خودروهای ایرانی با دستگاه", 2_500_000),
    ("تعویض روغن گیربکس کلیه خودروهای اتوماتیک با دستگاه", 6_000_000),
    ("تعویض روغن هیدرولیک فرمان کلیه خودروهای خارجی", 2_500_000),
    ("تعویض روغن گیربکس خودروهای دنده‌ای", 1_600_000),
    ("تعویض فیلتر گیربکس اتوماتیک", 7_000_000),
    ("تعویض خنک کن گیربکس اتوماتیک", 9_000_000),
]


class Command(BaseCommand):
    help = "ثبت کالای خدماتی «تعویض روغن» و نرخ‌نامه ۱۴۰۵ برای اتحادیه تعمیرکاران اتومبیل"

    def add_arguments(self, parser):
        parser.add_argument("--union", default="تعمیرکاران", help="بخشی از نام اتحادیه (پیش‌فرض: تعمیرکاران)")

    @transaction.atomic
    def handle(self, *args, **opts):
        unions = list(Union.objects.filter(name__icontains=opts["union"]))
        if len(unions) != 1:
            names = ", ".join(u.name for u in Union.objects.all()) or "—"
            self.stderr.write(self.style.ERROR(
                f"اتحادیه‌ای که نامش شامل «{opts['union']}» باشد دقیقاً یکی پیدا نشد ({len(unions)} مورد). "
                f"اتحادیه‌های موجود: {names}\nابتدا اتحادیه را بسازید یا با --union نام درست را بدهید."
            ))
            return
        union = unions[0]
        product, created = Product.objects.get_or_create(
            union=union, name=PRODUCT_NAME,
            defaults={"unit": Unit.PIECE, "is_service": True, "description": "نرخ‌نامه خدمات تعویض روغن و فیلتر — سال ۱۴۰۵"},
        )
        if not product.is_service:
            product.is_service = True
        product.is_active = True
        product.price_changed_at = timezone.now()
        product.save()
        product.tariffs.all().delete()
        ServiceTariff.objects.bulk_create(
            ServiceTariff(product=product, order=i, title=t, price=p) for i, (t, p) in enumerate(TARIFFS, 1)
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'ساخته شد' if created else 'به‌روز شد'}: «{PRODUCT_NAME}» زیر {union.name} با {len(TARIFFS)} ردیف نرخ‌نامه"
        ))
