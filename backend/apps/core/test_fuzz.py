"""آزمون دودِ ورودی‌های خراب: هیچ نشانی API با ورودی نامعتبر نباید خطای ۵۰۰ بدهد.

همه نشانی‌های /api/ پیدا می‌شوند و با چند نقش و چند بدنه‌ی خراب (نوع اشتباه، خیلی بزرگ، خالی، فهرست به‌جای شیء)
صدا زده می‌شوند. پاسخ ۵۰۰ یعنی ورودیِ کاربر بدون اعتبارسنجی به منطق رسیده است.
"""
import re
import traceback

from django.urls import get_resolver
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.core.tests import Base
from apps.orgs.models import Store
from apps.shop.models import ShopProduct

GARBAGE = [
    {},
    {"x": None},
    [],
    "text",
    {"mobile": 5, "amount": "abc", "items": "x", "orders": 5, "bundles": {"a": 1}, "note": ["a"], "price": "1e99", "quantity": -1,
     "status": 7, "value": {"a": 1}, "reason": 5, "name": 5, "title": [], "address": {}, "lat": "north", "lng": [1], "product": "abc",
     "courier": "zz", "supplier": [], "date": "not-a-date", "payment_method": 3, "delivery": 9, "password": 5, "code": 7,
     "first_name": 3, "last_name": [], "union": "u", "category": "c", "kind": 1, "mode": 1},
    {"price": 10**30, "amount": 10**30, "qty": 10**30, "stock": 10**30, "items": [{"product": 10**30, "qty": 10**30, "unit_cost": 10**30}],
     "value": 10**30, "fee_per_delivery": 10**30, "min_stock": 10**30, "cost_price": 10**30, "quantity": 10**30},
]

SKIP = ("django-admin", "schema", "docs", "backup/restore", "auth/token/refresh")


def _urls():
    def walk(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            else:
                yield prefix + str(p.pattern)

    seen = set()
    for raw in walk(get_resolver().url_patterns):
        if "format" in raw or "\\." in raw:
            continue
        u = raw.replace("^", "").replace("$", "").replace("\\Z", "")
        u = re.sub(r"<int:\w+>", "1", u)
        u = re.sub(r"<str:\w+>", "ABC1", u)
        u = re.sub(r"\(\?P<\w+>[^)]*\)", "1", u)
        if not u.startswith("api/") or any(s in u for s in SKIP) or "<" in u or "(" in u:
            continue
        if u not in seen:
            seen.add(u)
            yield "/" + u


class FuzzTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.fowner = User.objects.create_user("09125551111", role=Role.STORE)
        cls.fstore = Store.objects.create(owner=cls.fowner, name="ویژه", address="همدان", status=Store.Status.ACTIVE, is_featured=True)
        ShopProduct.objects.create(store=cls.fstore, name="برنج", price=1_000_000, status="approved", stock=5)

    def test_no_endpoint_returns_500_on_garbage(self):
        users = {
            "anon": None, "admin": self.admin, "union": self.uni, "chamber": self.cham, "gov": self.gov, "store": self.stores[0].owner,
            "featured": self.fowner, "citizen": self.citizen,
        }
        bad = []
        urls = list(_urls())
        self.assertGreater(len(urls), 80)                       # مطمئن شویم نشانی‌ها واقعا پیدا شده‌اند
        for who, user in users.items():
            c = APIClient(raise_request_exception=True)
            if user:
                c.force_authenticate(user)
            for url in urls:
                for method in ("get", "post", "patch", "put"):
                    payloads = GARBAGE if method != "get" else [None]
                    for body in payloads:
                        try:
                            if method == "get":
                                resp = c.get(url, {"page": "x", "product": "abc", "supplier": "abc", "county": "z", "category": "k", "from": "bad",
                                                   "to": "bad", "status": "?", "ordering": "<>"})
                            else:
                                resp = getattr(c, method)(url, body, format="json")
                            if resp.status_code >= 500:
                                bad.append(f"{who} {method.upper()} {url} HTTP{resp.status_code}")
                        except Exception as e:  # noqa: BLE001
                            frames = [f for f in traceback.extract_tb(e.__traceback__) if "nazerbazar" in f.filename and "site-packages" not in f.filename]
                            where = f"{frames[-1].filename.split('backend')[-1]}:{frames[-1].lineno}" if frames else "?"
                            bad.append(f"{who} {method.upper()} {url} {type(e).__name__}: {str(e)[:70]} @ {where}")
        # هر نشانی تکراری را یک‌بار گزارش بده
        uniq = sorted({b.split(" ", 1)[1] for b in bad})
        self.assertEqual(uniq, [], "نشانی‌های دارای خطای ۵۰۰:\n" + "\n".join(uniq))

    def test_anonymous_cannot_reach_protected_endpoints(self):
        """هر نشانی غیرعمومی بدون ورود باید رد شود (۴۰۱/۴۰۳)؛ فقط /api/public/ و /api/auth/ و چند فهرست پایه باز است."""
        open_ok = ("/api/public/", "/api/auth/", "/api/categories/", "/api/shop-categories/", "/api/commodities/")
        c = APIClient(raise_request_exception=False)
        leaks = []
        for u in _urls():
            if u.startswith(open_ok):
                continue
            for method in ("get", "post", "patch", "delete"):
                resp = getattr(c, method)(u) if method in ("get", "delete") else getattr(c, method)(u, {}, format="json")
                if resp.status_code not in (401, 403, 404, 405):
                    leaks.append(f"{method.upper()} {u} → {resp.status_code}")
        self.assertEqual(leaks, [], "نشانی‌های باز بدون ورود:\n" + "\n".join(leaks))
