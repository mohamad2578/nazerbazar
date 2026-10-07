"""هم‌ترازکردن شمارنده شناسه جدول‌ها (sequence) با داده موجود.

بعد از بازیابی پشتیبان روی PostgreSQL، رکوردها با شناسه مشخص درج می‌شوند و شمارنده
جدول عقب می‌ماند؛ نتیجه‌اش خطای «duplicate key value violates unique constraint» در
اولین رکورد جدید است. این دستور آن را درست می‌کند و اجرای دوباره‌اش بی‌خطر است.

اجرا: python manage.py fix_sequences
"""
from django.core.management.base import BaseCommand

from apps.core.backup import reset_sequences


class Command(BaseCommand):
    help = "رفع خطای تکراری بودن شناسه بعد از بازیابی پشتیبان (هم‌ترازی sequenceها)"

    def handle(self, *args, **opts):
        n = reset_sequences()
        self.stdout.write(self.style.SUCCESS(f"شمارنده {n} جدول هم‌تراز شد."))
