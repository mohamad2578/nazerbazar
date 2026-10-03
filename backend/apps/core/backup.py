"""پشتیبان‌گیری و بازیابی اطلاعات سامانه (ویژه مدیر کل).

خروجی یک فایل ZIP است شامل:
  • data.json  → تمام رکوردهای دیتابیس به قالب استاندارد جنگو (dumpdata)
  • media/     → فایل‌های آپلودشده (تصویر کالا، اسلایدها، مستندات شکایت و ...)
  • meta.json  → نسخه، تاریخ و شمارش رکوردها برای اعتبارسنجی هنگام بازیابی

بازیابی، داده فعلی همان جدول‌ها را با داده فایل جایگزین می‌کند؛ به همین دلیل پیش از
هر بازیابی یک پشتیبان خودکار از وضعیت فعلی در پوشه backups ساخته می‌شود.
"""
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management import call_command
from django.db import transaction

FORMAT_VERSION = 1

# اپ‌هایی که داده‌شان پشتیبان‌گیری می‌شود (جدول‌های سیستمی جنگو کنار گذاشته می‌شوند)
APP_LABELS = ["accounts", "orgs", "market", "shop", "complaints", "observatory", "distribution", "cms"]

# این مدل‌ها لاگ/موقتی هستند و به پشتیبان نیازی ندارند
EXCLUDED_MODELS = {"accounts.otp", "accounts.notification"}


def _models():
    for label in APP_LABELS:
        for model in apps.get_app_config(label).get_models():
            name = f"{model._meta.app_label}.{model._meta.model_name}"
            if name not in EXCLUDED_MODELS:
                yield name, model


def counts() -> dict:
    return {name: model.objects.count() for name, model in _models()}


def create_backup() -> tuple[bytes, str]:
    """ساخت فایل پشتیبان و برگرداندن (محتوای فایل، نام پیشنهادی)."""
    data = io.StringIO()
    call_command(
        "dumpdata",
        *[name for name, _ in _models()],
        format="json",
        indent=1,
        natural_foreign=True,
        stdout=data,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", data.getvalue())
        zf.writestr(
            "meta.json",
            json.dumps(
                {"version": FORMAT_VERSION, "created_at": datetime.now().isoformat(), "counts": counts()},
                ensure_ascii=False,
                indent=1,
            ),
        )
        media = Path(settings.MEDIA_ROOT)
        if media.exists():
            for f in media.rglob("*"):
                if f.is_file() and "backups" not in f.parts:
                    zf.write(f, f"media/{f.relative_to(media).as_posix()}")
    return buf.getvalue(), f"nazer724-backup-{stamp}.zip"


def _snapshot_before_restore() -> Path:
    """پشتیبان خودکار از وضعیت فعلی، پیش از بازیابی."""
    content, name = create_backup()
    folder = Path(settings.MEDIA_ROOT) / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"auto-{name}"
    path.write_bytes(content)
    return path


def inspect(file) -> dict:
    """خواندن اطلاعات فایل پشتیبان بدون اعمال آن."""
    with zipfile.ZipFile(file) as zf:
        if "data.json" not in zf.namelist():
            raise ValueError("فایل انتخابی یک پشتیبان معتبر سامانه نیست.")
        meta = json.loads(zf.read("meta.json")) if "meta.json" in zf.namelist() else {}
        media_files = [n for n in zf.namelist() if n.startswith("media/") and not n.endswith("/")]
    return {
        "version": meta.get("version"),
        "created_at": meta.get("created_at"),
        "counts": meta.get("counts", {}),
        "media_files": len(media_files),
    }


@transaction.atomic
def restore(file, with_media: bool = True) -> dict:
    """بازیابی داده از فایل پشتیبان. رکوردهای موجود با همان شناسه بازنویسی می‌شوند."""
    info = inspect(file)
    if info["version"] not in (None, FORMAT_VERSION):
        raise ValueError("نسخه فایل پشتیبان با این نسخه سامانه سازگار نیست.")
    snapshot = _snapshot_before_restore()

    file.seek(0)
    with zipfile.ZipFile(file) as zf:
        payload = zf.read("data.json").decode("utf-8")
        restored = 0
        for obj in serializers.deserialize("json", payload, ignorenonexistent=True):
            obj.save()
            restored += 1
        media_count = 0
        if with_media:
            media_root = Path(settings.MEDIA_ROOT)
            for name in zf.namelist():
                if not name.startswith("media/") or name.endswith("/"):
                    continue
                target = media_root / name[len("media/") :]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
                media_count += 1
    return {
        "restored": restored,
        "media_files": media_count,
        "counts": counts(),
        "snapshot": snapshot.name,
    }
