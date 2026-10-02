"""انتقال داده از نسخه لاراول (بک‌آپ MySQL): استان، شهرستان‌ها، اتاق اصناف، اتحادیه‌ها و کالاها با نرخ مصوب.

python manage.py import_legacy "nazerbaz_maindb.sql" --province 16
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.utils import to_en_digits
from apps.market.models import Category, OfficialPrice, Product, Unit
from apps.observatory.models import Commodity
from apps.orgs.models import Chamber, County, Province, Union

CATEGORY_BY_UNION = [
    ("قصاب", "گوشت و پروتئین"), ("مرغ", "مرغ و ماهی"), ("میوه", "میوه و تره‌بار"), ("خوار", "خواربار"),
]


def parse_inserts(sql: str, table: str):
    """ردیف‌های INSERT INTO `table` (...) VALUES (...),(...); را به dict تبدیل می‌کند."""
    rows = []
    pattern = re.compile(rf"INSERT INTO `{table}` \((.*?)\) VALUES\s*(.*?);\s*$", re.S | re.M)
    for m in pattern.finditer(sql):
        cols = [c.strip(" `") for c in m.group(1).split(",")]
        for values in _tuples(m.group(2)):
            rows.append(dict(zip(cols, values)))
    return rows


def _tuples(s: str):
    i, n = 0, len(s)
    while i < n:
        if s[i] != "(":
            i += 1
            continue
        i += 1
        vals, cur, in_str = [], [], False
        while i < n:
            ch = s[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    cur.append({"n": "\n", "r": "\r", "t": "\t"}.get(s[i + 1], s[i + 1]))
                    i += 2
                    continue
                if ch == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    in_str = False
                else:
                    cur.append(ch)
            elif ch == "'":
                in_str = True
                cur = []
            elif ch in ",)":
                raw = "".join(cur).strip()
                vals.append(None if raw == "NULL" else raw)
                cur = []
                if ch == ")":
                    i += 1
                    break
            else:
                cur.append(ch)
            i += 1
        yield vals


def guess_unit(name: str):
    n = to_en_digits(name)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(کیلو|گرم|لیتر|عدد)", n)
    if m:
        amount = float(m.group(1))
        return {"کیلو": Unit.KG, "گرم": Unit.GRAM, "لیتر": Unit.LITER, "عدد": Unit.PIECE}[m.group(2)], amount
    if "لیتر" in n:
        return Unit.LITER, 1
    if "عدد" in n:
        return Unit.PIECE, 1
    return Unit.KG, 1


def guess_commodity(name: str, commodities):
    for c in commodities:
        key = c.name.split()[0]
        if len(key) > 2 and key in name:
            if key == "برنج" and "پاکستانی" not in name:
                continue
            return c
    return None


class Command(BaseCommand):
    help = "انتقال داده از بک‌آپ MySQL نسخه قبلی"

    def add_arguments(self, parser):
        parser.add_argument("sql_path")
        parser.add_argument("--province", type=int, default=16, help="شناسه استان در دیتابیس قدیمی")

    @transaction.atomic
    def handle(self, sql_path, province, **opts):
        try:
            sql = open(sql_path, encoding="utf8").read()
        except OSError as e:
            raise CommandError(str(e))
        states = {r["id"]: r for r in parse_inserts(sql, "state")}
        if str(province) not in states:
            raise CommandError("استان در فایل یافت نشد.")
        pname = re.sub(r"^.*\((.*)\)$", r"\1", states[str(province)]["name"]).strip()
        prov, _ = Province.objects.get_or_create(name=pname)

        counties = {}
        for r in parse_inserts(sql, "city"):
            if r["state_id"] == str(province):
                counties[r["id"]], _ = County.objects.get_or_create(province=prov, name=r["name"].strip())

        chambers = {}
        for r in parse_inserts(sql, "caste"):
            county = counties.get(r["city_id"])
            if county:
                chambers[r["id"]], _ = Chamber.objects.get_or_create(
                    county=county, name=r["title"].strip(), defaults={"address": r["address"] or "", "phone": r["phone"] or ""}
                )

        unions = {}
        for r in parse_inserts(sql, "union"):
            chamber = chambers.get(r["caste_id"])
            if chamber:
                unions[r["id"]], _ = Union.objects.get_or_create(
                    chamber=chamber, name=r["title"].strip(),
                    defaults={"address": r["address"] or "", "phone": r["phone"] or "",
                              "lat": _dec(r.get("lat")), "lng": _dec(r.get("long"))},
                )

        commodities = list(Commodity.objects.all())
        cats = {c.name: c for c in Category.objects.all()}
        created = 0
        for r in parse_inserts(sql, "product"):
            union = unions.get(r["union_id"])
            if not union or not r["title"]:
                continue
            name = r["title"].strip()
            price = int(float(r["min_price"] or 0))
            unit, amount = guess_unit(name)
            cat_name = next((c for k, c in CATEGORY_BY_UNION if k in union.name), None)
            product, is_new = Product.objects.get_or_create(
                union=union, name=name,
                defaults={"unit": unit, "unit_amount": amount, "category": cats.get(cat_name),
                          "commodity": guess_commodity(name, commodities)},
            )
            if is_new and price:
                product.current_price = price
                product.price_changed_at = timezone.now()
                product.save()
                OfficialPrice.objects.create(product=product, price=price, note="انتقال از نسخه قبلی")
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f"استان {prov.name}: {len(counties)} شهرستان، {len(chambers)} اتاق اصناف، {len(unions)} اتحادیه، {created} کالا"
        ))


def _dec(v):
    try:
        return round(float(v), 6) if v else None
    except ValueError:
        return None
