"""محدودسازی داده‌ها بر اساس جایگاه کاربر در سلسله‌مراتب:
استان (استانداری) -> شهرستان -> اتاق اصناف -> اتحادیه -> فروشگاه
هر مدل مسیر lookup خود تا هر سطح را در دیکشنری SCOPE معرفی می‌کند؛
مقدار می‌تواند یک مسیر یا چند مسیر (tuple، با OR) باشد.
"""
from django.db.models import Q

ROLE_FIELD = {"governorate": "province_id", "chamber": "chamber_id", "union": "union_id"}
ROLE_LEVEL = {"governorate": "province", "chamber": "chamber", "union": "union"}


def _any(paths, value) -> Q:
    if isinstance(paths, str):
        paths = (paths,)
    q = Q()
    for p in paths:
        q |= Q(**{p: value})
    return q


def scope_filter(user, paths: dict) -> Q:
    role = getattr(user, "role", None)
    if role == "admin":
        return Q()
    level = ROLE_LEVEL.get(role)
    if level and level in paths:
        value = getattr(user, ROLE_FIELD[role])
        return _any(paths[level], value) if value else Q(pk__in=[])
    if role == "store" and "store" in paths:
        path = paths["store"]
        return Q(owner=user.pk) if path == "self" else Q(**{f"{path}__owner": user.pk})
    return Q(pk__in=[])


def scoped(qs, user, paths: dict):
    return qs.filter(scope_filter(user, paths))
