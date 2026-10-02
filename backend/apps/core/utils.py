import math
import random
import re
import string

from django.core.exceptions import ValidationError

_FA = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
_EN = "01234567890123456789"
_DIGITS = str.maketrans(_FA, _EN)


def to_en_digits(value: str) -> str:
    return (value or "").translate(_DIGITS)


def normalize_mobile(value: str) -> str:
    """۰۹۱۲... ، +98912... و 98912... را به قالب 09xxxxxxxxx تبدیل می‌کند."""
    v = re.sub(r"[\s\-]", "", to_en_digits(value))
    if v.startswith("+98"):
        v = "0" + v[3:]
    elif v.startswith("98") and len(v) == 12:
        v = "0" + v[2:]
    elif v.startswith("9") and len(v) == 10:
        v = "0" + v
    if not re.fullmatch(r"09\d{9}", v):
        raise ValidationError({"mobile": "شماره موبایل معتبر نیست."})
    return v


def random_code(length=6, alphabet=string.digits) -> str:
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


def tracking_code(prefix="") -> str:
    return prefix + random_code(8, "23456789ABCDEFGHJKLMNPQRSTUVWXYZ")


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def percent_change(old, new):
    if not old:
        return None
    return round((float(new) - float(old)) / float(old) * 100, 2)
