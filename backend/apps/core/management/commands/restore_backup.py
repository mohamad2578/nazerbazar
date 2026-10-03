"""بازیابی فایل پشتیبان از خط فرمان سرور (جایگزین پنل، وقتی دسترسی به رابط وب نداریم).

    python manage.py restore_backup /path/to/nazer724-backup.zip
    python manage.py restore_backup backup.zip --no-media
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core import backup


class Command(BaseCommand):
    help = "بازیابی داده و فایل‌ها از فایل پشتیبان ZIP"

    def add_arguments(self, parser):
        parser.add_argument("path", help="مسیر فایل پشتیبان")
        parser.add_argument("--no-media", action="store_true", help="فقط داده بازیابی شود، بدون تصاویر")

    def handle(self, path, **opts):
        f = Path(path)
        if not f.exists():
            raise CommandError(f"فایل پیدا نشد: {path}")
        with f.open("rb") as fh:
            info = backup.inspect(fh)
            self.stdout.write(f"پشتیبان ساخته‌شده در {info['created_at']} — {info['media_files']} فایل تصویر")
            fh.seek(0)
            result = backup.restore(fh, with_media=not opts["no_media"])
        self.stdout.write(self.style.SUCCESS(
            f"{result['restored']} رکورد و {result['media_files']} فایل بازیابی شد. "
            f"پشتیبان خودکار پیش از بازیابی: {result['snapshot']}"
        ))
