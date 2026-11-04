"""تست قواعد اصلی: سقف/کف قیمت، مهلت ۲۴ ساعته، مرتب‌سازی، دسترسی سلسله‌مراتبی، شکایت و توزیع."""
from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OTP, Role, User
from apps.complaints.models import Complaint
from apps.distribution.models import Allocation, Quota
from apps.market.models import Product, StoreOffer
from apps.market.services import set_official_price, upsert_offer, visible_offers
from apps.observatory.models import Commodity
from apps.orgs.models import Chamber, County, Province, Store, Union


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prov = Province.objects.create(name="همدان")
        cls.prov2 = Province.objects.create(name="تهران")
        cls.county = County.objects.create(province=cls.prov, name="همدان")
        cls.chamber = Chamber.objects.create(county=cls.county, name="اتاق اصناف همدان")
        cls.union = Union.objects.create(chamber=cls.chamber, name="خواربار")
        cls.other_union = Union.objects.create(
            chamber=Chamber.objects.create(county=County.objects.create(province=cls.prov2, name="ری"), name="ری"),
            name="خواربار ری",
        )
        cls.admin = User.objects.create_user("09120000000", role=Role.ADMIN)
        cls.gov = User.objects.create_user("09120000001", role=Role.GOVERNORATE, province=cls.prov)
        cls.cham = User.objects.create_user("09120000002", role=Role.CHAMBER, chamber=cls.chamber)
        cls.uni = User.objects.create_user("09120000003", role=Role.UNION, union=cls.union)
        cls.uni2 = User.objects.create_user("09120000004", role=Role.UNION, union=cls.other_union)
        cls.citizen = User.objects.create_user("09120000009")
        cls.stores = []
        for i, (lat, lng) in enumerate([(34.80, 48.51), (34.81, 48.52), (34.79, 48.50)]):
            owner = User.objects.create_user(f"0912000010{i}", role=Role.STORE)
            cls.stores.append(Store.objects.create(
                owner=owner, union=cls.union, name=f"فروشگاه {i}", address="همدان", lat=lat, lng=lng,
                status=Store.Status.ACTIVE,
            ))
        cls.product = Product.objects.create(union=cls.union, name="شکر", unit="kg")
        set_official_price(cls.product, 1_000_000, cls.cham)

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class PriceRulesTests(Base):
    def test_offer_must_be_between_80_and_100_percent(self):
        s = self.stores[0]
        with self.assertRaises(Exception):
            upsert_offer(s, self.product, 1_000_001)
        with self.assertRaises(Exception):
            upsert_offer(s, self.product, 799_999)
        self.assertEqual(upsert_offer(s, self.product, 800_000).price, 800_000)
        self.assertEqual(upsert_offer(s, self.product, 1_000_000).price, 1_000_000)

    def test_custom_discount_limit(self):
        set_official_price(self.product, 1_000_000, self.cham, max_discount=10)
        with self.assertRaises(Exception):
            upsert_offer(self.stores[0], self.product, 850_000)

    def test_inactive_store_and_foreign_product_rejected(self):
        s = self.stores[0]
        s.status = Store.Status.PENDING
        s.save()
        with self.assertRaises(Exception):
            upsert_offer(s, self.product, 900_000)
        foreign = Product.objects.create(union=self.other_union, name="برنج", current_price=100)
        with self.assertRaises(Exception):
            upsert_offer(self.stores[1], foreign, 100)

    def test_stale_offer_is_never_hidden_after_24_hours(self):
        """قاعده حذف پس از ۲۴ ساعت برداشته شده: قیمت اعلامی قبلی باقی می‌ماند و نمایش داده می‌شود."""
        s = self.stores[0]
        offer = upsert_offer(s, self.product, 900_000)
        set_official_price(self.product, 1_200_000, self.cham)
        self.assertIn(offer.pk, visible_offers().values_list("pk", flat=True))
        offer.refresh_from_db()
        self.assertTrue(offer.is_stale)
        Product.objects.filter(pk=self.product.pk).update(price_changed_at=timezone.now() - timedelta(hours=25))
        StoreOffer.objects.filter(pk=offer.pk).update(confirmed_at=timezone.now() - timedelta(hours=26))
        self.assertIn(offer.pk, visible_offers().values_list("pk", flat=True))
        # ناموجود شدن توسط خود فروشگاه همچنان از فهرست خارج می‌کند
        StoreOffer.objects.filter(pk=offer.pk).update(is_available=False)
        self.assertNotIn(offer.pk, visible_offers().values_list("pk", flat=True))

    def test_same_price_does_not_reset_deadline(self):
        offer = upsert_offer(self.stores[0], self.product, 900_000)
        changed = self.product.price_changed_at
        set_official_price(self.product, 1_000_000, self.cham)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_changed_at, changed)
        offer.refresh_from_db()
        self.assertFalse(offer.is_stale)

    def test_store_notified_on_price_change(self):
        upsert_offer(self.stores[0], self.product, 900_000)
        set_official_price(self.product, 1_100_000, self.cham)
        self.assertTrue(self.stores[0].owner.notifications.filter(title__contains="تغییر حداکثر قیمت").exists())


class PublicApiTests(Base):
    def test_offers_sorted_by_price_ascending(self):
        for s, price in zip(self.stores, [950_000, 820_000, 900_000]):
            upsert_offer(s, self.product, price)
        r = APIClient().get(f"/api/public/products/{self.product.pk}/", {"lat": 34.8, "lng": 48.51})
        self.assertEqual(r.status_code, 200)
        prices = [o["price"] for o in r.data["offers"]]
        self.assertEqual(prices, [820_000, 900_000, 950_000])
        self.assertIsNotNone(r.data["offers"][0]["distance_km"])
        self.assertEqual(r.data["offers"][0]["store"]["name"], "فروشگاه 1")

    def test_product_list_shows_min_price(self):
        upsert_offer(self.stores[0], self.product, 850_000)
        r = APIClient().get("/api/public/products/")
        row = next(x for x in r.data["results"] if x["id"] == self.product.pk)
        self.assertEqual(row["min_price"], 850_000)
        self.assertEqual(row["offers_count"], 1)


class ScopeTests(Base):
    def test_union_sees_only_own_stores(self):
        other_owner = User.objects.create_user("09129999999")
        Store.objects.create(owner=other_owner, union=self.other_union, name="ری", address="ری")
        r = self.client_for(self.uni).get("/api/stores/")
        self.assertEqual(r.data["count"], 3)

    def test_union_cannot_price_other_union_product(self):
        r = self.client_for(self.uni2).post(f"/api/products/{self.product.pk}/set_price/", {"price": 5})
        self.assertEqual(r.status_code, 404)

    def test_union_creates_product_with_price_awaiting_approval(self):
        r = self.client_for(self.uni).post("/api/products/", {"name": "عدس", "unit": "kg", "initial_price": 300000})
        self.assertEqual(r.status_code, 201, r.data)
        p = Product.objects.get(pk=r.data["id"])
        # کالا ساخته می‌شود ولی نرخ اولیه اتحادیه تا تایید اتاق اصناف اعمال نمی‌شود
        self.assertEqual((p.union_id, p.current_price), (self.union.pk, 0))
        pending = p.price_history.get()
        self.assertEqual((pending.status, pending.price), ("pending", 300000))
        self.client_for(self.cham).post(f"/api/prices/{pending.pk}/review/", {"approve": True})
        p.refresh_from_db()
        self.assertEqual(p.current_price, 300000)

    def test_governorate_cannot_create_county_in_other_province(self):
        c = self.client_for(self.gov)
        self.assertEqual(c.post("/api/counties/", {"province": self.prov.pk, "name": "ملایر"}).status_code, 201)
        self.assertEqual(c.post("/api/counties/", {"province": self.prov2.pk, "name": "شمیران"}).status_code, 403)

    def test_chamber_can_only_create_union_users(self):
        c = self.client_for(self.cham)
        ok = c.post("/api/users/", {"mobile": "09121111111", "role": "union", "union": self.union.pk})
        self.assertEqual(ok.status_code, 201, ok.data)
        bad = c.post("/api/users/", {"mobile": "09121111112", "role": "governorate", "province": self.prov.pk})
        self.assertEqual(bad.status_code, 400)

    def test_store_approval_flow(self):
        owner = User.objects.create_user("09128888888")
        c = self.client_for(owner)
        r = c.post("/api/my-store/", {
            "name": "جدید", "union": self.union.pk, "address": "همدان", "lat": 34.8, "lng": 48.5,
            "first_name": "رضا", "last_name": "احمدی", "national_code": "0012345678",
        })
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "pending")
        self.assertTrue(self.uni.notifications.filter(title__contains="فعال‌سازی").exists())
        store_id = r.data["id"]
        u = self.client_for(self.uni)
        self.assertEqual(u.post(f"/api/stores/{store_id}/reject/", {}).status_code, 400)  # دلیل الزامی
        self.assertEqual(u.post(f"/api/stores/{store_id}/approve/").status_code, 200)
        owner.refresh_from_db()
        self.assertEqual(owner.role, Role.STORE)


class ComplaintTests(Base):
    def test_complaint_routes_to_union_with_copy_to_chamber(self):
        upsert_offer(self.stores[0], self.product, 900_000)
        c = self.client_for(self.citizen)
        r = c.post("/api/public/complaints/", {
            "store": self.stores[0].pk, "product": self.product.pk, "kind": "overprice",
            "paid_price": 1_100_000, "description": "گران‌فروشی",
        })
        self.assertEqual(r.status_code, 201, r.data)
        comp = Complaint.objects.get(tracking_code=r.data["tracking_code"])
        self.assertEqual((comp.union, comp.chamber, comp.announced_price, comp.official_price),
                         (self.union, self.chamber, 900_000, 1_000_000))
        self.assertTrue(self.uni.notifications.exists())
        self.assertTrue(self.cham.notifications.filter(title__contains="رونوشت").exists())
        # اتحادیه دیگر دسترسی ندارد
        self.assertEqual(self.client_for(self.uni2).get(f"/api/complaints/{comp.pk}/").status_code, 404)
        # بستن بدون نتیجه رسیدگی مجاز نیست
        u = self.client_for(self.uni)
        self.assertEqual(u.post(f"/api/complaints/{comp.pk}/transition/", {"status": "resolved"}).status_code, 400)
        r = u.post(f"/api/complaints/{comp.pk}/transition/", {"status": "resolved", "note": "تذکر", "violation_confirmed": True})
        self.assertEqual(r.status_code, 200)
        # پیگیری عمومی
        t = APIClient().get("/api/public/complaints/track/", {"code": comp.tracking_code, "mobile": "09120000009"})
        self.assertEqual(t.data["status"], "resolved")
        # فروشگاه هویت شاکی را نمی‌بیند
        s = self.client_for(self.stores[0].owner).get(f"/api/complaints/{comp.pk}/")
        self.assertNotIn("reporter_mobile", s.data)
        self.assertNotIn("reporter_name", s.data)


class OtpTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_with_otp(self):
        c = APIClient()
        r = c.post("/api/auth/otp/request/", {"mobile": "۰۹۱۲۳۴۵۶۷۸۹"})
        self.assertEqual(r.status_code, 200, r.data)
        code = OTP.objects.get(mobile="09123456789").code
        self.assertEqual(c.post("/api/auth/otp/verify/", {"mobile": "09123456789", "code": "0000"}).status_code, 400)
        r = c.post("/api/auth/otp/verify/", {"mobile": "09123456789", "code": code})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertEqual(r.data["user"]["role"], "citizen")


class DistributionTests(Base):
    def test_quota_flow_and_capacity(self):
        com = Commodity.objects.create(name="برنج")
        a = Allocation.objects.create(
            province=self.prov, commodity=com, title="برنج", total_quantity=1000, allocation_price=100,
            consumer_price=120, starts_on=timezone.localdate(), status=Allocation.Status.ACTIVE,
        )
        g = self.client_for(self.gov)
        self.assertEqual(g.post(f"/api/allocations/{a.pk}/set_share/", {"union": self.union.pk, "quantity": 1200}).status_code, 400)
        self.assertEqual(g.post(f"/api/allocations/{a.pk}/set_share/", {"union": self.union.pk, "quantity": 600}).status_code, 200)
        share = a.shares.get()
        u = self.client_for(self.uni)
        r = u.post(f"/api/shares/{share.pk}/assign/", {"items": [{"store": self.stores[0].pk, "quantity": 400}]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r2 = u.post(f"/api/shares/{share.pk}/assign/", {"items": [{"store": self.stores[1].pk, "quantity": 300}]}, format="json")
        self.assertEqual(r2.status_code, 400)
        q = Quota.objects.get()
        store_client = self.client_for(self.stores[0].owner)
        self.assertEqual(store_client.post(f"/api/quotas/{q.pk}/advance/", {"status": "dispatched"}).status_code, 400)
        self.assertEqual(u.post(f"/api/quotas/{q.pk}/advance/", {"status": "dispatched"}).status_code, 200)
        r = store_client.post(f"/api/quotas/{q.pk}/advance/", {"status": "received", "received_quantity": 380})
        self.assertEqual(r.status_code, 200, r.data)
        rows = self.client_for(self.gov).get("/api/analytics/distribution/").data
        self.assertEqual(rows[0]["delivery_gap"], 20)
        self.assertEqual(len(APIClient().get("/api/public/subsidized/").data), 1)


class AnalyticsTests(Base):
    def test_overview_and_exports(self):
        upsert_offer(self.stores[0], self.product, 900_000)
        from apps.market.services import take_daily_snapshot

        take_daily_snapshot()
        for user in (self.admin, self.gov, self.cham, self.uni):
            c = self.client_for(user)
            self.assertEqual(c.get("/api/analytics/overview/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/trends/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/unions/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/counties/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/basket/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/complaints/").status_code, 200)
            self.assertEqual(c.get("/api/analytics/export/prices/").status_code, 200)
        data = self.client_for(self.uni2).get("/api/analytics/overview/").data
        self.assertEqual(data["stores"]["total"], 0)


class ShopTests(Base):
    """فروشگاه اینترنتی: محصولات اختصاصی فروشگاه، بدون محدودیت نرخ مصوب اتحادیه."""

    def test_store_manages_own_products_with_free_price(self):
        store = self.stores[0]
        c = self.client_for(store.owner)
        r = c.post("/api/shop-products/", {"name": "زعفران", "price": 9_500_000, "unit": "piece"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["store"], store.pk)
        # قیمت آزاد است: برخلاف کالای اساسی، سقف/کف نرخ مصوب اعمال نمی‌شود
        self.assertEqual(r.data["price"], 9_500_000)
        pid = r.data["id"]
        self.assertEqual(c.patch(f"/api/shop-products/{pid}/", {"price": 12_000_000}).status_code, 200)
        self.assertEqual(c.delete(f"/api/shop-products/{pid}/").status_code, 204)

    def test_store_cannot_touch_other_store_products(self):
        from apps.shop.models import ShopProduct

        mine = ShopProduct.objects.create(store=self.stores[0], name="کالای من", price=1000)
        other = self.client_for(self.stores[1].owner)
        self.assertEqual(other.get(f"/api/shop-products/{mine.pk}/").status_code, 404)
        self.assertEqual(other.patch(f"/api/shop-products/{mine.pk}/", {"price": 5}).status_code, 404)
        # فروشگاه دوم فقط محصولات خودش را می‌بیند
        self.assertEqual(other.get("/api/shop-products/").data["count"], 0)

    def test_pending_store_cannot_add_products(self):
        store = self.stores[0]
        store.status = Store.Status.PENDING
        store.save()
        r = self.client_for(store.owner).post("/api/shop-products/", {"name": "x", "price": 100})
        self.assertEqual(r.status_code, 400)

    def test_public_shop_shows_only_approved_and_active_products(self):
        from apps.shop.models import ShopProduct

        store = self.stores[0]
        ok = ShopProduct.Status.APPROVED
        ShopProduct.objects.create(store=store, name="نمایش‌داده‌شده", price=1000, status=ok)
        ShopProduct.objects.create(store=store, name="پنهان", price=2000, is_active=False, status=ok)
        ShopProduct.objects.create(store=store, name="در انتظار تایید صمت", price=3000)
        rows = APIClient().get(f"/api/public/stores/{store.pk}/shop/").data
        self.assertEqual([r["name"] for r in rows], ["نمایش‌داده‌شده"])

    def test_union_sees_member_store_products_readonly(self):
        from apps.shop.models import ShopProduct

        ShopProduct.objects.create(store=self.stores[0], name="کالا", price=1000)
        union = self.client_for(self.uni)
        self.assertEqual(union.get("/api/shop-products/").data["count"], 1)
        # اتحادیه در این بخش دخالتی ندارد؛ فقط مشاهده
        self.assertEqual(union.post("/api/shop-products/", {"name": "y", "price": 1}).status_code, 403)
        self.assertEqual(self.client_for(self.uni2).get("/api/shop-products/").data["count"], 0)


class StoreLocationTests(Base):
    def test_union_can_set_store_location_and_map_lists_it(self):
        store = self.stores[0]
        Store.objects.filter(pk=store.pk).update(lat=None, lng=None)
        self.assertNotIn(store.pk, [s["id"] for s in APIClient().get("/api/public/map/").data])
        r = self.client_for(self.uni).patch(f"/api/stores/{store.pk}/", {"lat": 34.79, "lng": 48.51})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn(store.pk, [s["id"] for s in APIClient().get("/api/public/map/").data])

    def test_store_owner_updates_own_location(self):
        store = self.stores[1]
        r = self.client_for(store.owner).patch("/api/my-store/", {"lat": 34.80, "lng": 48.52})
        self.assertEqual(r.status_code, 200, r.data)
        store.refresh_from_db()
        self.assertEqual(float(store.lat), 34.80)


class PriceSnapTests(Base):
    """اگر مدیر «هم‌ترازی قیمت فروشگاه‌ها» را روشن کند، با تغییر حداکثر قیمت قیمت همه برابر آن می‌شود."""

    def setUp(self):
        from apps.core.models import SystemSettings

        s = SystemSettings.get()
        s.snap_store_prices = True
        s.save()

    def test_offers_snap_to_new_official_price(self):
        s0, s1 = self.stores[0], self.stores[1]
        upsert_offer(s0, self.product, 850_000)   # ۱۵٪ زیر نرخ
        upsert_offer(s1, self.product, 1_000_000)  # برابر نرخ
        set_official_price(self.product, 1_200_000, self.cham)
        self.assertEqual([o.price for o in StoreOffer.objects.filter(product=self.product).order_by("pk")],
                         [1_200_000, 1_200_000])
        # همچنان «در انتظار به‌روزرسانی» است تا فروشگاه تایید/اصلاح کند
        self.assertTrue(StoreOffer.objects.get(store=s0, product=self.product).is_stale)
        # و فروشگاه می‌تواند دوباره تا سقف تخفیف مجاز قیمت را کم کند
        upsert_offer(s0, self.product, 960_000)
        offer = StoreOffer.objects.get(store=s0, product=self.product)
        self.assertEqual(offer.price, 960_000)
        self.assertFalse(offer.is_stale)

    def test_unchanged_price_does_not_touch_offers(self):
        upsert_offer(self.stores[0], self.product, 850_000)
        set_official_price(self.product, 1_000_000, self.cham)  # همان نرخ قبلی
        self.assertEqual(StoreOffer.objects.get(store=self.stores[0]).price, 850_000)


class StoreApprovalRolesTests(Base):
    """تایید فروشگاه علاوه بر اتحادیه، توسط اتاق اصناف/استانداری/مدیر کل هم ممکن است."""

    def _pending_store(self):
        owner = User.objects.create_user(f"0912777{Store.objects.count():04d}")
        return Store.objects.create(owner=owner, union=self.union, name="جدید", address="همدان",
                                    status=Store.Status.PENDING)

    def test_chamber_and_governorate_and_admin_can_approve(self):
        for actor in (self.cham, self.gov, self.admin):
            store = self._pending_store()
            r = self.client_for(actor).post(f"/api/stores/{store.pk}/approve/")
            self.assertEqual(r.status_code, 200, f"{actor.role}: {r.data}")
            store.refresh_from_db()
            self.assertEqual(store.status, Store.Status.ACTIVE)

    def test_store_owner_cannot_approve_itself(self):
        store = self._pending_store()
        self.assertEqual(self.client_for(store.owner).post(f"/api/stores/{store.pk}/approve/").status_code, 403)


class OrderTests(Base):
    """سفارش از ویترین فروشگاه و گردش آن در کارتابل فروشنده."""

    def setUp(self):
        from apps.shop.models import ShopProduct

        self.store = self.stores[0]
        self.p1 = ShopProduct.objects.create(store=self.store, name="عسل", price=500_000, unit="piece",
                                                status="approved")
        self.p2 = ShopProduct.objects.create(store=self.store, name="زعفران", price=900_000, unit="g",
                                                status="approved")

    def _place(self, **extra):
        body = {"items": [{"product": self.p1.pk, "quantity": 2}, {"product": self.p2.pk, "quantity": 1}],
                "customer_name": "علی", "customer_phone": "09120000009", **extra}
        return self.client_for(self.citizen).post(f"/api/public/stores/{self.store.pk}/order/", body, format="json")

    def test_order_lands_in_store_panel_with_correct_total(self):
        r = self._place()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["total"], 2 * 500_000 + 900_000)
        self.assertEqual(r.data["status"], "new")
        # فروشنده آن را در کارتابل خود می‌بیند و صاحب فروشگاه اعلان گرفته است
        panel = self.client_for(self.store.owner).get("/api/orders/")
        self.assertEqual(panel.data["count"], 1)
        self.assertTrue(self.store.owner.notifications.filter(title__contains="سفارش جدید").exists())
        # فروشگاه دیگر این سفارش را نمی‌بیند
        self.assertEqual(self.client_for(self.stores[1].owner).get("/api/orders/").data["count"], 0)

    def test_store_moves_order_through_statuses(self):
        oid = self._place().data["id"]
        c = self.client_for(self.store.owner)
        for status in ("confirmed", "preparing", "ready", "delivered"):
            r = c.post(f"/api/orders/{oid}/transition/", {"status": status})
            self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(c.get("/api/orders/summary/").data["delivered"], 1)
        # پس از تحویل، تغییر وضعیت دیگر مجاز نیست
        self.assertEqual(c.post(f"/api/orders/{oid}/transition/", {"status": "preparing"}).status_code, 400)

    def test_customer_can_cancel_only_before_preparing(self):
        code = self._place().data["code"]
        c = self.client_for(self.citizen)
        self.assertEqual(len(c.get("/api/public/orders/mine/").data), 1)
        oid = self._place().data["id"]
        self.client_for(self.store.owner).post(f"/api/orders/{oid}/transition/", {"status": "confirmed"})
        self.client_for(self.store.owner).post(f"/api/orders/{oid}/transition/", {"status": "preparing"})
        self.assertEqual(c.post(f"/api/public/orders/{code}/cancel/").status_code, 200)
        second_code = [o["code"] for o in c.get("/api/public/orders/mine/").data if o["id"] == oid][0]
        self.assertEqual(c.post(f"/api/public/orders/{second_code}/cancel/").status_code, 400)

    def test_unavailable_product_is_rejected(self):
        self.p1.is_available = False
        self.p1.save()
        self.assertEqual(self._place().status_code, 400)

    def test_delivery_requires_address(self):
        r = self._place(delivery="delivery")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._place(delivery="delivery", address="همدان، خیابان اول").status_code, 201)


class BackupTests(Base):
    """پشتیبان‌گیری و بازیابی — فقط مدیر کل."""

    def test_only_admin_can_use_backup(self):
        for user in (self.gov, self.cham, self.uni, self.citizen):
            self.assertEqual(self.client_for(user).get("/api/backup/status/").status_code, 403, user.role)
        self.assertEqual(self.client_for(self.admin).get("/api/backup/status/").status_code, 200)

    def test_backup_download_and_restore_recovers_deleted_rows(self):
        from apps.shop.models import ShopProduct

        ShopProduct.objects.create(store=self.stores[0], name="کالای مهم", price=123_000)
        c = self.client_for(self.admin)

        r = c.get("/api/backup/download/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/zip")
        archive = r.content

        # حذف عمدی و سپس بازیابی
        ShopProduct.objects.all().delete()
        self.stores[0].refresh_from_db()
        self.assertEqual(ShopProduct.objects.count(), 0)

        upload = SimpleUploadedFile("b.zip", archive, content_type="application/zip")
        r = c.post("/api/backup/restore/", {"file": upload, "confirm": "true"}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(ShopProduct.objects.filter(name="کالای مهم").count(), 1)

    def test_restore_requires_confirmation_and_valid_file(self):
        c = self.client_for(self.admin)
        archive = c.get("/api/backup/download/").content
        no_confirm = SimpleUploadedFile("b.zip", archive, content_type="application/zip")
        self.assertEqual(c.post("/api/backup/restore/", {"file": no_confirm}, format="multipart").status_code, 400)
        junk = SimpleUploadedFile("x.zip", b"not a zip", content_type="application/zip")
        self.assertEqual(
            c.post("/api/backup/restore/", {"file": junk, "confirm": "true"}, format="multipart").status_code, 400
        )

    def test_inspect_reports_contents(self):
        c = self.client_for(self.admin)
        archive = c.get("/api/backup/download/").content
        upload = SimpleUploadedFile("b.zip", archive, content_type="application/zip")
        info = c.post("/api/backup/inspect/", {"file": upload}, format="multipart").data
        self.assertEqual(info["version"], 1)
        self.assertEqual(info["counts"]["orgs.store"], Store.objects.count())


class SamtAndPriceApprovalTests(Base):
    """اداره صمت (بالادست اتاق اصناف) و گردش تایید نرخ مصوب."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000005", role=Role.SAMT, province=cls.prov)
        cls.samt2 = User.objects.create_user("09120000006", role=Role.SAMT, province=cls.prov2)

    def test_union_price_waits_for_chamber_approval(self):
        before = self.product.current_price
        rec = set_official_price(self.product, 1_300_000, self.uni)
        self.product.refresh_from_db()
        # نرخ هنوز اعمال نشده است
        self.assertEqual(rec.status, "pending")
        self.assertEqual(self.product.current_price, before)
        # اتاق اصناف و اداره صمت آن را در کارتابل می‌بینند
        for user in (self.cham, self.samt):
            rows = self.client_for(user).get("/api/prices/pending/").data["results"]
            self.assertEqual([r["id"] for r in rows], [rec.pk], user.role)
        # اتحادیه دیگر استان آن را نمی‌بیند
        self.assertEqual(self.client_for(self.samt2).get("/api/prices/pending/").data["count"], 0)
        self.assertTrue(self.cham.notifications.filter(title__contains="در انتظار تایید").exists())

        r = self.client_for(self.cham).post(f"/api/prices/{rec.pk}/review/", {"approve": True})
        self.assertEqual(r.status_code, 200, r.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_price, 1_300_000)
        self.assertTrue(self.uni.notifications.filter(title__contains="تایید شد").exists())

    def test_rejected_price_is_not_applied_and_needs_reason(self):
        rec = set_official_price(self.product, 2_000_000, self.uni)
        c = self.client_for(self.cham)
        self.assertEqual(c.post(f"/api/prices/{rec.pk}/review/", {"approve": False}).status_code, 400)
        r = c.post(f"/api/prices/{rec.pk}/review/", {"approve": False, "note": "نرخ غیرواقعی است"})
        self.assertEqual(r.status_code, 200, r.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_price, 1_000_000)
        self.assertTrue(self.uni.notifications.filter(title__contains="رد شد").exists())
        # بررسی دوباره مجاز نیست
        self.assertEqual(c.post(f"/api/prices/{rec.pk}/review/", {"approve": True}).status_code, 400)

    def test_samt_price_applies_immediately(self):
        rec = set_official_price(self.product, 1_400_000, self.samt)
        self.product.refresh_from_db()
        self.assertEqual(rec.status, "approved")
        self.assertEqual(self.product.current_price, 1_400_000)

    def test_union_cannot_review_prices(self):
        rec = set_official_price(self.product, 1_200_000, self.uni)
        self.assertEqual(self.client_for(self.uni).get("/api/prices/pending/").status_code, 403)
        self.assertEqual(self.client_for(self.uni).post(f"/api/prices/{rec.pk}/review/", {"approve": True}).status_code, 403)

    def test_newer_union_price_supersedes_previous_pending(self):
        first = set_official_price(self.product, 1_100_000, self.uni)
        second = set_official_price(self.product, 1_150_000, self.uni)
        first.refresh_from_db()
        self.assertEqual(first.status, "rejected")
        self.assertEqual(second.status, "pending")
        rows = self.client_for(self.cham).get("/api/prices/pending/").data["results"]
        self.assertEqual([r["id"] for r in rows], [second.pk])

    def test_samt_bulk_upload_sets_prices(self):
        from openpyxl import load_workbook

        c = self.client_for(self.samt)
        r = c.get("/api/prices/bulk-template/")
        self.assertEqual(r.status_code, 200)
        wb = load_workbook(BytesIO(r.content))
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        self.assertEqual(rows[0][0], self.product.pk)

        # پر کردن ستون «نرخ جدید» و بارگذاری
        ws.cell(2, 6, 1_750_000)
        buf = BytesIO()
        wb.save(buf)
        upload = SimpleUploadedFile("p.xlsx", buf.getvalue())
        preview = c.post("/api/prices/bulk-upload/", {"file": upload, "dry_run": "true"}, format="multipart").data
        self.assertEqual(preview["changes"][0]["new_price"], 1_750_000)
        self.assertEqual(preview["applied"], 0)

        buf.seek(0)
        upload = SimpleUploadedFile("p.xlsx", buf.getvalue())
        out = c.post("/api/prices/bulk-upload/", {"file": upload}, format="multipart").data
        self.assertEqual(out["applied"], 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_price, 1_750_000)

    def test_bulk_upload_rejects_products_outside_scope(self):
        foreign = Product.objects.create(union=self.other_union, name="بیرونی", current_price=100)
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["شناسه کالا", "نام", "اتحادیه", "واحد", "فعلی", "نرخ جدید", "تخفیف", "توضیح"])
        ws.append([foreign.pk, foreign.name, "", "", 100, 999, 20, ""])
        buf = BytesIO()
        wb.save(buf)
        out = self.client_for(self.samt).post(
            "/api/prices/bulk-upload/", {"file": SimpleUploadedFile("p.xlsx", buf.getvalue())}, format="multipart"
        ).data
        self.assertEqual(out["applied"], 0)
        self.assertEqual(len(out["errors"]), 1)
        foreign.refresh_from_db()
        self.assertEqual(foreign.current_price, 100)

    def test_samt_can_manage_structure_like_governorate(self):
        c = self.client_for(self.samt)
        self.assertEqual(c.get("/api/stores/").status_code, 200)
        self.assertEqual(c.get("/api/analytics/overview/").status_code, 200)
        # صمت می‌تواند کاربر اتاق اصناف بسازد
        r = c.post("/api/users/", {"mobile": "09125550001", "role": "chamber", "chamber": self.chamber.pk})
        self.assertEqual(r.status_code, 201, r.data)
        # ولی نمی‌تواند کاربر استانداری بسازد
        self.assertEqual(
            c.post("/api/users/", {"mobile": "09125550002", "role": "governorate", "province": self.prov.pk}).status_code,
            400,
        )


class SamtManagementTests(Base):
    """اداره صمت: مدیریت اتحادیه‌ها و مدیریت کامل کالاها."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000007", role=Role.SAMT, province=cls.prov)
        cls.samt_other = User.objects.create_user("09120000008", role=Role.SAMT, province=cls.prov2)

    def test_samt_creates_and_edits_unions_and_chambers(self):
        c = self.client_for(self.samt)
        r = c.post("/api/chambers/", {"county": self.county.pk, "name": "اتاق اصناف جدید"})
        self.assertEqual(r.status_code, 201, r.data)
        chamber_id = r.data["id"]
        r = c.post("/api/unions/", {"chamber": chamber_id, "name": "اتحادیه نانوایان", "guild": "نان"})
        self.assertEqual(r.status_code, 201, r.data)
        union_id = r.data["id"]
        r = c.patch(f"/api/unions/{union_id}/", {"name": "اتحادیه نانوایان سنتی", "is_active": False})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Union.objects.get(pk=union_id).name, "اتحادیه نانوایان سنتی")
        # اتحادیه استان دیگر برای این صمت قابل دیدن/ویرایش نیست
        self.assertEqual(self.client_for(self.samt_other).get(f"/api/unions/{union_id}/").status_code, 404)

    def test_samt_creates_product_for_a_union_and_can_reassign_it(self):
        c = self.client_for(self.samt)
        second = Union.objects.create(chamber=self.chamber, name="اتحادیه دوم")
        r = c.post("/api/products/", {"name": "شکر", "unit": "kg", "union": self.union.pk, "initial_price": 900_000})
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["id"]
        p = Product.objects.get(pk=pid)
        # نرخ اداره صمت بدون نیاز به تایید اعمال می‌شود
        self.assertEqual((p.union_id, p.current_price), (self.union.pk, 900_000))
        # تخصیص کالا به اتحادیه دیگر
        r = c.patch(f"/api/products/{pid}/", {"union": second.pk})
        self.assertEqual(r.status_code, 200, r.data)
        p.refresh_from_db()
        self.assertEqual(p.union_id, second.pk)
        # غیرفعال‌سازی کالا
        self.assertEqual(c.delete(f"/api/products/{pid}/").status_code, 204)
        p.refresh_from_db()
        self.assertFalse(p.is_active)

    def test_samt_cannot_touch_products_outside_province(self):
        foreign = Product.objects.create(union=self.other_union, name="بیرونی", current_price=100)
        c = self.client_for(self.samt)
        self.assertEqual(c.get(f"/api/products/{foreign.pk}/").status_code, 404)
        self.assertEqual(c.patch(f"/api/products/{foreign.pk}/", {"name": "x"}).status_code, 404)
        # و نمی‌تواند کالا را به اتحادیه خارج از حوزه خود منتقل کند
        mine = Product.objects.create(union=self.union, name="مال من", current_price=100)
        self.assertEqual(c.patch(f"/api/products/{mine.pk}/", {"union": self.other_union.pk}).status_code, 403)

    def test_union_cannot_move_its_product_to_another_union(self):
        second = Union.objects.create(chamber=self.chamber, name="اتحادیه سوم")
        r = self.client_for(self.uni).patch(f"/api/products/{self.product.pk}/", {"union": second.pk})
        self.assertEqual(r.status_code, 200, r.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.union_id, self.union.pk)  # تغییری نکرده


class SamtStoreManagementTests(Base):
    """اداره صمت: تعریف فروشگاه، ویرایش مشخصات و بازنشانی رمز عبور مالک."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000011", role=Role.SAMT, province=cls.prov)
        cls.samt_other = User.objects.create_user("09120000012", role=Role.SAMT, province=cls.prov2)

    def _new_store(self, client=None, **over):
        body = {"union": self.union.pk, "name": "فروشگاه صمت", "address": "همدان، میدان بوعلی",
                "owner_mobile": "09351112233", "owner_first_name": "رضا", "owner_last_name": "کریمی",
                "password": "storepass123"}
        body.update(over)
        return (client or self.client_for(self.samt)).post("/api/stores/", body)

    def test_samt_creates_an_active_store_with_its_owner_account(self):
        r = self._new_store()
        self.assertEqual(r.status_code, 201, r.data)
        store = Store.objects.get(pk=r.data["id"])
        self.assertEqual(store.status, Store.Status.ACTIVE)
        self.assertEqual(store.reviewed_by, self.samt)
        owner = store.owner
        self.assertEqual((owner.mobile, owner.role, owner.first_name), ("09351112233", Role.STORE, "رضا"))
        self.assertTrue(owner.check_password("storepass123"))
        # مالک می‌تواند بلافاصله وارد پنل شود
        self.assertEqual(self.client.post("/api/auth/login/",
                         {"mobile": "09351112233", "password": "storepass123"}).status_code, 200)

    def test_samt_edits_store_details_and_owner_mobile(self):
        store = Store.objects.get(pk=self._new_store().data["id"])
        c = self.client_for(self.samt)
        r = c.patch(f"/api/stores/{store.pk}/", {"name": "هایپر صمت", "phone": "08134000000",
                                                 "owner_mobile": "09351119999", "owner_last_name": "کریمی‌نژاد"})
        self.assertEqual(r.status_code, 200, r.data)
        store.refresh_from_db()
        store.owner.refresh_from_db()
        self.assertEqual(store.name, "هایپر صمت")
        self.assertEqual((store.owner.mobile, store.owner.last_name), ("09351119999", "کریمی‌نژاد"))
        self.assertEqual(r.data["owner_mobile"], "09351119999")

    def test_samt_resets_store_password(self):
        store = Store.objects.get(pk=self._new_store().data["id"])
        c = self.client_for(self.samt)
        self.assertEqual(c.post(f"/api/stores/{store.pk}/set_password/", {"password": "123"}).status_code, 400)
        r = c.post(f"/api/stores/{store.pk}/set_password/", {"password": "tazeh-ramz-1404"})
        self.assertEqual(r.status_code, 200, r.data)
        store.owner.refresh_from_db()
        self.assertTrue(store.owner.check_password("tazeh-ramz-1404"))

    def test_duplicate_owner_mobile_and_out_of_scope_union_are_rejected(self):
        self._new_store()
        self.assertEqual(self._new_store().status_code, 400)
        # اتحادیه خارج از استان این صمت
        other_union = Union.objects.create(
            chamber=Chamber.objects.create(county=County.objects.create(province=self.prov2, name="ملایر"),
                                           name="اتاق دیگر"), name="اتحادیه دیگر")
        r = self._new_store(union=other_union.pk, owner_mobile="09351114444")
        self.assertIn(r.status_code, (400, 403))

    def test_union_can_also_create_a_store_but_only_in_its_own_union(self):
        r = self._new_store(self.client_for(self.uni), owner_mobile="09351115555")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Store.objects.get(pk=r.data["id"]).union, self.union)


class OtherGoodsApprovalTests(Base):
    """کالاهای غیراساسی: قیمت آزاد است اما تا تایید کارشناس صمت عمومی نمی‌شود."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000013", role=Role.SAMT, province=cls.prov)

    def _add(self, **over):
        body = {"name": "زعفران قائنات", "price": 9_500_000, "unit": "piece",
                "is_active": True, "is_available": True}
        body.update(over)
        return self.client_for(self.stores[0].owner).post("/api/shop-products/", body, format="json")

    def test_new_product_waits_for_samt_and_is_hidden_from_public(self):
        from apps.shop.models import ShopProduct

        r = self._add()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], ShopProduct.Status.PENDING)
        # ویترین عمومی فروشگاه هنوز آن را نشان نمی‌دهد
        pub = self.client.get(f"/api/public/stores/{self.stores[0].pk}/shop/")
        self.assertEqual([p["id"] for p in pub.data], [])

        pid = r.data["id"]
        c = self.client_for(self.samt)
        self.assertEqual(c.get("/api/other-prices/", {"status": "pending"}).data["count"], 1)
        self.assertEqual(c.post(f"/api/other-prices/{pid}/approve/").status_code, 200)

        pub = self.client.get(f"/api/public/stores/{self.stores[0].pk}/shop/")
        self.assertEqual([p["id"] for p in pub.data], [pid])
        self.assertEqual(self.client.get("/api/public/shop-products/").data["count"], 1)

    def test_rejection_needs_a_reason_and_keeps_product_hidden(self):
        pid = self._add().data["id"]
        c = self.client_for(self.samt)
        self.assertEqual(c.post(f"/api/other-prices/{pid}/reject/").status_code, 400)
        r = c.post(f"/api/other-prices/{pid}/reject/", {"note": "قیمت غیرمتعارف است"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "rejected")
        self.assertEqual(self.client.get(f"/api/public/stores/{self.stores[0].pk}/shop/").data, [])

    def test_price_edit_sends_an_approved_product_back_to_the_queue(self):
        pid = self._add().data["id"]
        samt = self.client_for(self.samt)
        samt.post(f"/api/other-prices/{pid}/approve/")
        owner = self.client_for(self.stores[0].owner)

        # تغییر فیلد بی‌اثر تاییدیه را باطل نمی‌کند
        owner.patch(f"/api/shop-products/{pid}/", {"is_available": False}, format="json")
        self.assertEqual(owner.get(f"/api/shop-products/{pid}/").data["status"], "approved")

        # اما تغییر قیمت، دوباره نیاز به تایید دارد
        r = owner.patch(f"/api/shop-products/{pid}/", {"price": 15_000_000}, format="json")
        self.assertEqual(r.data["status"], "pending", r.data)
        self.assertEqual(self.client.get(f"/api/public/stores/{self.stores[0].pk}/shop/").data, [])

    def test_union_may_watch_but_only_samt_approves(self):
        pid = self._add().data["id"]
        uni = self.client_for(self.uni)
        self.assertEqual(uni.get("/api/other-prices/").data["count"], 1)      # می‌بیند
        self.assertEqual(uni.post(f"/api/other-prices/{pid}/approve/").status_code, 403)  # تایید نمی‌کند
        # صمت استان دیگر اصلا این محصول را نمی‌بیند
        other = User.objects.create_user("09120000014", role=Role.SAMT, province=self.prov2)
        self.assertEqual(self.client_for(other).get(f"/api/other-prices/{pid}/").status_code, 404)


class ReviewAuthTests(Base):
    """ثبت نظر و امتیاز فقط برای کاربر واردشده به سامانه ممکن است."""

    def test_anonymous_cannot_review_but_logged_in_citizen_can(self):
        url = f"/api/public/stores/{self.stores[0].pk}/reviews/"
        self.assertEqual(self.client.post(url, {"rating": 5}).status_code, 401)
        r = self.client_for(self.citizen).post(url, {"rating": 5, "comment": "عالی بود"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rating_count"], 1)


class ChainStoreTests(Base):
    """فروشگاه فاقد اتحادیه (زنجیره‌ای، جهاد، حامی): روی کالاهای اتحادیه‌های تحت پوشش قیمت می‌دهد."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000015", role=Role.SAMT, province=cls.prov)
        cls.second = Union.objects.create(chamber=cls.chamber, name="اتحادیه دوم")
        cls.prod2 = Product.objects.create(union=cls.second, name="شکر", unit="kg")
        set_official_price(cls.prod2, 500_000, cls.cham)

    def _chain(self, client=None, **over):
        body = {"name": "فروشگاه زنجیره‌ای رفاه", "address": "همدان، بلوار ارم",
                "owner_mobile": "09371234567", "password": "chainpass123",
                "union": None, "covered_unions": [self.union.pk, self.second.pk]}
        body.update(over)
        return (client or self.client_for(self.samt)).post("/api/stores/", body, format="json")

    def test_store_without_union_covers_several_unions(self):
        r = self._chain()
        self.assertEqual(r.status_code, 201, r.data)
        store = Store.objects.get(pk=r.data["id"])
        self.assertIsNone(store.union)
        self.assertCountEqual(store.priceable_union_ids(), [self.union.pk, self.second.pk])
        self.assertIn("فاقد اتحادیه", r.data["union_name"])
        self.assertEqual(r.data["county_name"], "همدان")

        # روی کالای هر دو اتحادیه می‌تواند قیمت بدهد
        upsert_offer(store, self.product, self.product.current_price, True)
        upsert_offer(store, self.prod2, self.prod2.current_price, True)
        self.assertEqual(store.offers.count(), 2)

    def test_either_union_or_covered_unions_is_required(self):
        r = self._chain(covered_unions=[])
        self.assertEqual(r.status_code, 400)
        self.assertIn("covered_unions", r.data)
        # و نمی‌توان هم‌زمان هر دو را داشت
        r = self._chain(union=self.union.pk, owner_mobile="09371234568")
        self.assertEqual(r.status_code, 400)
        self.assertIn("union", r.data)

    def test_chain_store_cannot_price_a_union_it_does_not_cover(self):
        store = Store.objects.get(pk=self._chain(covered_unions=[self.second.pk]).data["id"])
        with self.assertRaises(ValidationError):
            upsert_offer(store, self.product, self.product.current_price, True)

    def test_officials_see_the_chain_store_through_its_covered_unions(self):
        sid = self._chain(covered_unions=[self.union.pk]).data["id"]
        # اتحادیه تحت پوشش آن را در کارتابل خود می‌بیند
        self.assertEqual(self.client_for(self.uni).get(f"/api/stores/{sid}/").status_code, 200)
        # اتحادیه‌ای که پوشش داده نشده، نمی‌بیند
        self.assertEqual(self.client_for(self.uni2).get(f"/api/stores/{sid}/").status_code, 404)
        # اتاق اصناف و صمت استان می‌بینند
        self.assertEqual(self.client_for(self.cham).get(f"/api/stores/{sid}/").status_code, 200)
        self.assertEqual(self.client_for(self.samt).get(f"/api/stores/{sid}/").status_code, 200)

    def test_store_panel_lists_products_of_every_covered_union(self):
        store = Store.objects.get(pk=self._chain().data["id"])
        rows = self.client_for(store.owner).get("/api/store/catalog/").data["items"]
        names = {r["name"] for r in rows}
        self.assertIn(self.product.name, names)
        self.assertIn("شکر", names)


class CitizenRegisterTests(Base):
    """ثبت‌نام شهروند با موبایل و رمز؛ حساب موجود را بازنویسی نمی‌کند."""

    def setUp(self):
        cache.clear()  # محدودیت نرخ ثبت‌نام بین تست‌ها ریست شود

    def _reg(self, **over):
        body = {"mobile": "09351230000", "password": "citizen-pass-1", "first_name": "علی", "last_name": "احمدی"}
        body.update(over)
        return APIClient().post("/api/auth/register/", body, format="json")

    def test_citizen_registers_and_can_log_in_with_password(self):
        r = self._reg()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["user"]["role"], Role.CITIZEN)
        self.assertEqual(APIClient().post("/api/auth/login/",
                         {"mobile": "09351230000", "password": "citizen-pass-1"}).status_code, 200)

    def test_registration_cannot_take_over_an_existing_account(self):
        self.assertEqual(self._reg(mobile="09120000001").status_code, 400)  # کاربر استانداری
        self._reg()
        self.assertEqual(self._reg(password="another-pass-2").status_code, 400)

    def test_short_password_and_missing_name_are_rejected(self):
        r = self._reg(password="123", first_name="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)
        self.assertIn("first_name", r.data)


class NewsAndSupplierTests(Base):
    """اخبار (منتشر‌شده برای عموم، ثبت توسط صمت) و فرم تامین‌کنندگان."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000016", role=Role.SAMT, province=cls.prov)

    def setUp(self):
        cache.clear()

    def test_samt_publishes_news_and_public_sees_only_published(self):
        from apps.news.models import NewsItem

        c = self.client_for(self.samt)
        r = c.post("/api/news/", {"title": "اطلاعیه توزیع", "body": "متن خبر", "is_published": True}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        draft = c.post("/api/news/", {"title": "پیش‌نویس", "body": "x", "is_published": False}, format="json")
        self.assertEqual(draft.status_code, 201)
        titles = [n["title"] for n in self.client.get("/api/public/news/").data]
        self.assertEqual(titles, ["اطلاعیه توزیع"])
        self.assertEqual(self.client.get(f"/api/public/news/{draft.data['id']}/").status_code, 404)
        self.assertEqual(NewsItem.objects.get(pk=r.data["id"]).created_by, self.samt)

    def test_union_cannot_write_news(self):
        r = self.client_for(self.uni).post("/api/news/", {"title": "x", "body": "y"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_public_supplier_form_validates_and_deduplicates_by_mobile(self):
        from apps.suppliers.models import Supplier

        url = "/api/public/suppliers/"
        self.assertEqual(APIClient().post(url, {"first_name": "", "mobile": "x"}, format="json").status_code, 400)
        body = {"first_name": "علی", "last_name": "رضایی", "mobile": "09351234500", "product_type": "لبنیات"}
        self.assertEqual(APIClient().post(url, body, format="json").status_code, 201)
        body["product_type"] = "لبنیات و تخم مرغ"
        APIClient().post(url, body, format="json")
        self.assertEqual(Supplier.objects.filter(mobile="09351234500").count(), 1)
        self.assertEqual(self.client_for(self.samt).get("/api/suppliers/").data[0]["product_type"], "لبنیات و تخم مرغ")
        self.assertEqual(self.client_for(self.uni).get("/api/suppliers/").status_code, 403)

    def test_products_get_categories_from_their_names(self):
        from apps.market.services import assign_categories
        from apps.market.models import Category

        Category.objects.create(name="خواربار", order=1)
        Category.objects.create(name="میوه و تره‌بار", order=2)
        Product.objects.create(union=self.union, name="برنج هندی", unit="kg")
        Product.objects.create(union=self.union, name="سیب زمینی", unit="kg")
        self.assertEqual(assign_categories(), 2)
        self.assertEqual(Product.objects.get(name="برنج هندی").category.name, "خواربار")


    def test_news_image_upload_is_saved_and_returned_as_url(self):
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, "JPEG")
        upload = SimpleUploadedFile("n.jpg", buf.getvalue(), content_type="image/jpeg")
        c = self.client_for(self.samt)
        r = c.post("/api/news/", {"title": "خبر دارای عکس", "body": "متن", "is_published": "true", "image": upload},
                   format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["image"] and "/media/news/" in r.data["image"], r.data["image"])
        public = self.client.get(f"/api/public/news/{r.data['id']}/").data
        self.assertIn("/media/news/", public["image"])

    def test_news_image_can_be_added_when_editing_an_existing_item(self):
        from PIL import Image

        c = self.client_for(self.samt)
        created = c.post("/api/news/", {"title": "بدون عکس", "body": "متن"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data["image"])

        buf = BytesIO()
        Image.new("RGB", (60, 60), (10, 120, 200)).save(buf, "JPEG")
        upload = SimpleUploadedFile("edit.jpg", buf.getvalue(), content_type="image/jpeg")
        # همان‌طور که فرم پنل می‌فرستد: PATCH چندبخشی با همه فیلدها
        r = c.patch(f"/api/news/{created.data['id']}/",
                    {"title": "بدون عکس", "body": "متن", "is_published": "true", "image": upload}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn("/media/news/", r.data["image"] or "")


class ChainStoreLoginAndActAsTests(Base):
    """ورود فروشگاه فاقد اتحادیه و قیمت‌دهی مسئول به جای فروشگاه."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000017", role=Role.SAMT, province=cls.prov)
        cls.samt_other = User.objects.create_user("09120000018", role=Role.SAMT, province=cls.prov2)

    def setUp(self):
        cache.clear()

    def test_union_less_store_owner_can_log_in(self):
        r = self.client_for(self.samt).post("/api/stores/", {
            "name": "فروشگاه پرسپولیس", "address": "همدان", "owner_mobile": "09011176787",
            "password": "chain-pass-1", "union": None, "covered_unions": [self.union.pk],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        login = APIClient().post("/api/auth/login/", {"mobile": "09011176787", "password": "chain-pass-1"})
        self.assertEqual(login.status_code, 200, login.content[:300])
        self.assertIn("فاقد اتحادیه", login.data["user"]["store"]["union_name"])

    def test_samt_prices_on_behalf_of_a_store_and_it_is_logged(self):
        from apps.market.models import OfferLog

        store = self.stores[0]
        c = self.client_for(self.samt)
        cat = c.get(f"/api/store/catalog/?store={store.pk}")
        self.assertEqual(cat.status_code, 200, cat.data)
        self.assertTrue(cat.data["store"]["acting_as"])
        price = self.product.current_price
        r = c.post(f"/api/store/offers/?store={store.pk}", [{"product": self.product.pk, "price": price}], format="json")
        self.assertEqual(r.status_code, 200, r.data)
        log = OfferLog.objects.filter(offer__store=store).latest("created_at")
        self.assertEqual(log.set_by, self.samt)

    def test_act_as_is_limited_by_role_and_province(self):
        store = self.stores[0]
        self.assertEqual(self.client_for(self.samt_other).get(f"/api/store/catalog/?store={store.pk}").status_code, 404)
        self.assertEqual(self.client_for(self.uni).get(f"/api/store/catalog/?store={store.pk}").status_code, 403)
        # فروشگاه دیگر نمی‌تواند به جای فروشگاه دیگری قیمت بدهد
        self.assertEqual(self.client_for(self.stores[1].owner).get(f"/api/store/catalog/?store={store.pk}").status_code, 403)

    def test_store_owner_pricing_is_unchanged(self):
        from apps.market.models import OfferLog

        owner = self.stores[0].owner
        r = self.client_for(owner).post("/api/store/offers/", [{"product": self.product.pk, "price": self.product.current_price}], format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(OfferLog.objects.filter(offer__store=self.stores[0]).latest("created_at").set_by)


class VisitAnalyticsTests(Base):
    """آمار بازدید: ثبت بازدید صفحه/کالا و گزارش برای مدیریت."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000019", role=Role.SAMT, province=cls.prov)

    def setUp(self):
        cache.clear()

    def _track(self, visitor, kind="page", path="/", product=None, ua=""):
        body = {"visitor": visitor, "kind": kind, "path": path}
        if product:
            body["product"] = product
        return APIClient().post("/api/public/track/", body, format="json", HTTP_USER_AGENT=ua)

    def test_tracking_and_report_counts(self):
        for v in ("a", "a", "b"):
            self.assertEqual(self._track(v, path="/").status_code, 204)
        self._track("c", path="/map", ua="Mozilla/5.0 Nazer724App/1.0")
        self._track("a", kind="product", path=f"/p/{self.product.pk}", product=self.product.pk)
        self._track("b", kind="product", path=f"/p/{self.product.pk}", product=self.product.pk)

        r = self.client_for(self.samt).get("/api/analytics/visits/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["page_views"], 4)
        self.assertEqual(r.data["visitors"], 3)
        self.assertEqual(r.data["product_views"], 2)
        self.assertEqual(r.data["platform"], {"web": 3, "app": 1})
        self.assertEqual(r.data["top_products"][0]["id"], self.product.pk)
        self.assertEqual(r.data["top_products"][0]["visitors"], 2)
        self.assertEqual(r.data["granularity"], "day")

    def test_short_range_is_hourly_and_validated(self):
        c = self.client_for(self.samt)
        r = c.get("/api/analytics/visits/", {"from": "2026-10-10T00:00", "to": "2026-10-11T00:00"})
        self.assertEqual(r.data["granularity"], "hour")
        self.assertEqual(c.get("/api/analytics/visits/", {"from": "2026-10-11", "to": "2026-10-10"}).status_code, 400)

    def test_only_management_sees_the_report_and_visitor_is_required(self):
        self.assertEqual(self.client_for(self.uni).get("/api/analytics/visits/").status_code, 403)
        self.assertEqual(APIClient().post("/api/public/track/", {"path": "/"}, format="json").status_code, 400)


    def test_every_product_is_listed_and_one_product_can_be_focused(self):
        other = Product.objects.create(union=self.union, name="کالای بدون کلیک", unit="kg")
        self._track("a", kind="product", path=f"/p/{self.product.pk}", product=self.product.pk)
        self._track("b", kind="product", path=f"/p/{self.product.pk}", product=self.product.pk)
        self._track("a", path=f"/s/{self.stores[0].pk}")
        c = self.client_for(self.samt)
        r = c.get("/api/analytics/visits/").data
        rows = {p["id"]: p for p in r["top_products"]}
        self.assertEqual(rows[self.product.pk]["views"], 2)
        self.assertEqual(rows[other.pk]["views"], 0)          # کالای بدون کلیک هم در فهرست هست
        self.assertEqual(r["top_stores"][0]["name"], self.stores[0].name)
        focused = c.get("/api/analytics/visits/", {"product": self.product.pk}).data
        self.assertEqual(focused["focus_product"], self.product.pk)
        self.assertEqual(sum(x["views"] for x in focused["series"]), 2)



class SpecialOfferTests(Base):
    """تخفیفات ویژه: فروشگاه تعریف می‌کند، صمت تایید می‌کند، مردم در صفحه تخفیفات می‌بینند."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000020", role=Role.SAMT, province=cls.prov)

    def setUp(self):
        cache.clear()

    def _offer(self, **over):
        body = {"name": "روغن سرخ‌کردنی ۱.۵ لیتری", "old_price": 2_000_000, "price": 1_600_000,
                "unit": "piece", "is_special": True, "is_active": True, "is_available": True}
        body.update(over)
        return self.client_for(self.stores[0].owner).post("/api/shop-products/", body, format="json")

    def test_offer_is_public_only_after_samt_approval(self):
        r = self._offer()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.client.get("/api/public/special-offers/").data["count"], 0)
        self.client_for(self.samt).post(f"/api/other-prices/{r.data['id']}/approve/")
        rows = self.client.get("/api/public/special-offers/").data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["discount_percent"], 20)
        self.assertEqual(rows[0]["store"]["id"], self.stores[0].pk)

    def test_special_offer_needs_a_real_discount(self):
        self.assertEqual(self._offer(old_price=None).status_code, 400)
        self.assertEqual(self._offer(old_price=1_500_000).status_code, 400)

    def test_offers_are_sorted_by_biggest_discount(self):
        a = self._offer(name="الف", old_price=1_000_000, price=900_000).data["id"]   # ۱۰٪
        b = self._offer(name="ب", old_price=1_000_000, price=600_000).data["id"]    # ۴۰٪
        for pid in (a, b):
            self.client_for(self.samt).post(f"/api/other-prices/{pid}/approve/")
        ids = [r["id"] for r in self.client.get("/api/public/special-offers/").data["results"]]
        self.assertEqual(ids, [b, a])


class SystemSettingsTests(Base):
    """تنظیمات مدیر کل: ثبت قیمت اتحادیه، رفتار قیمت فروشگاه‌ها، بخش‌های اتحادیه، گزارش‌های صمت و سابقه قیمت."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000021", role=Role.SAMT, province=cls.prov)

    def setUp(self):
        cache.clear()

    def _set(self, **data):
        r = self.client_for(self.admin).patch("/api/settings/", data, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def test_only_admin_changes_settings(self):
        self.assertEqual(self.client_for(self.samt).patch("/api/settings/", {"snap_store_prices": False}, format="json").status_code, 403)
        self.assertEqual(self.client_for(self.uni).get("/api/settings/").status_code, 200)

    def test_admin_can_stop_unions_from_setting_prices(self):
        url = f"/api/products/{self.product.pk}/set_price/"
        self.assertEqual(self.client_for(self.uni).post(url, {"price": self.product.current_price + 10_000}, format="json").status_code, 200)
        self._set(union_can_set_prices=False)
        r = self.client_for(self.uni).post(url, {"price": self.product.current_price + 20_000}, format="json")
        self.assertEqual(r.status_code, 400)
        # اداره صمت همچنان می‌تواند
        self.assertEqual(self.client_for(self.samt).post(url, {"price": self.product.current_price + 20_000}, format="json").status_code, 200)

    def test_keep_store_prices_when_snap_is_off(self):
        from apps.market.services import set_official_price

        offer = upsert_offer(self.stores[0], self.product, self.product.current_price - 1000, True)
        kept = offer.price
        self._set(snap_store_prices=False)
        set_official_price(self.product, self.product.current_price + 100_000, self.samt)
        offer.refresh_from_db()
        self.assertEqual(offer.price, kept)          # هنوز در بازه مجاز جدید است، پس دست‌نخورده می‌ماند
        set_official_price(self.product, kept - 50_000, self.samt)
        offer.refresh_from_db()
        self.assertEqual(offer.price, kept - 50_000)  # بالاتر از سقف جدید بود، به سقف آورده شد
        self._set(snap_store_prices=True)
        set_official_price(self.product, kept - 40_000, self.samt)
        offer.refresh_from_db()
        self.assertEqual(offer.price, kept - 40_000)  # حالت پیش‌فرض: برابر حداکثر قیمت

    def test_union_sections_are_enforced_on_the_server(self):
        self.assertEqual(self.client_for(self.uni).get("/api/stores/").status_code, 200)
        self._set(union_sections=["products"])
        self.assertEqual(self.client_for(self.uni).get("/api/stores/").status_code, 403)
        self.assertEqual(self.client_for(self.uni).get("/api/products/").status_code, 200)
        self.assertEqual(self.client_for(self.uni).get("/api/prices/log/").status_code, 403)
        # بقیه نقش‌ها تحت تاثیر نیستند
        self.assertEqual(self.client_for(self.cham).get("/api/stores/").status_code, 200)

    def test_admin_limits_which_reports_samt_sees(self):
        c = self.client_for(self.samt)
        self.assertEqual(c.get("/api/analytics/complaints/").status_code, 200)
        self._set(samt_reports=["prices"])
        self.assertEqual(c.get("/api/analytics/complaints/").status_code, 403)
        self.assertEqual(c.get("/api/analytics/visits/").status_code, 403)
        self.assertEqual(c.get("/api/analytics/price-changes/").status_code, 200)
        # استانداری محدود نمی‌شود
        self.assertEqual(self.client_for(self.gov).get("/api/analytics/complaints/").status_code, 200)

    def test_price_log_shows_who_and_when(self):
        from apps.market.services import set_official_price

        set_official_price(self.product, self.product.current_price + 30_000, self.samt, note="افزایش")
        # فقط مدیر کل و صمت؛ اتحادیه، اتاق اصناف و استانداری دسترسی ندارند
        for other in (self.uni, self.cham, self.gov):
            self.assertEqual(self.client_for(other).get("/api/prices/log/").status_code, 403)
        hist = self.client_for(self.uni).get(f"/api/products/{self.product.pk}/history/").data
        self.assertEqual(hist[0]["set_by_name"], "")
        rows = self.client_for(self.samt).get("/api/prices/log/", {"product": self.product.pk}).data["results"]
        latest = rows[0]
        self.assertEqual(latest["set_by_mobile"], self.samt.mobile)
        self.assertEqual(latest["set_by_role"], "اداره صمت")
        self.assertTrue(latest["created_at"])
        self.assertEqual(latest["note"], "افزایش")


class PriceChangeSmsTests(Base):
    """پیامک تغییر حداکثر قیمت به فروشگاه‌هایی که قیمت و موجودی اعلام کرده‌اند."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.samt = User.objects.create_user("09120000022", role=Role.SAMT, province=cls.prov)

    def test_default_keeps_the_stores_previous_price(self):
        offer = upsert_offer(self.stores[0], self.product, self.product.current_price - 1000)
        kept = offer.price
        set_official_price(self.product, self.product.current_price + 50_000, self.samt)
        offer.refresh_from_db()
        self.assertEqual(offer.price, kept)

    def test_only_stores_with_an_available_price_get_the_sms(self):
        from unittest import mock

        with_price = upsert_offer(self.stores[0], self.product, self.product.current_price - 1000)
        unavailable = upsert_offer(self.stores[1], self.product, self.product.current_price - 1000, is_available=False)
        no_price = self.stores[2]
        with mock.patch("apps.core.sms.send_price_change_sms") as sms:
            set_official_price(self.product, 650_000, self.samt)
        called = {c.args[0] for c in sms.call_args_list}
        self.assertEqual(called, {with_price.store.owner.mobile})
        self.assertNotIn(unavailable.store.owner.mobile, called)
        self.assertNotIn(no_price.owner.mobile, called)
        args = sms.call_args.args
        self.assertEqual((args[1], args[2], args[3]), (with_price.store.name, self.product.name, 65_000))

    def test_same_price_sends_nothing_and_admin_can_switch_it_off(self):
        from unittest import mock

        from apps.core.models import SystemSettings

        upsert_offer(self.stores[0], self.product, self.product.current_price - 1000)
        with mock.patch("apps.core.sms.send_price_change_sms") as sms:
            set_official_price(self.product, self.product.current_price, self.samt)
        sms.assert_not_called()
        s = SystemSettings.get()
        s.sms_on_price_change = False
        s.save()
        with mock.patch("apps.core.sms.send_price_change_sms") as sms:
            set_official_price(self.product, self.product.current_price + 10_000, self.samt)
        sms.assert_not_called()

    def test_message_text_and_ghasedak_driver(self):
        from unittest import mock

        from django.test import override_settings

        from apps.core import sms
        from apps.core.models import SmsLog

        text = sms.PRICE_CHANGE_TEXT.format(store="فروشگاه شهروند جولان", product="سیب زمینی", price="65,000")
        for part in ("فروشگاه شهروند جولان", "سیب زمینی", "65,000 تومان", "۲۴ ساعت", "مسئولیت آن بر عهده"):
            self.assertIn(part, text)
        with override_settings(SMS_BACKEND="ghasedak", GHASEDAK_API_KEY="key", GHASEDAK_LINE="3000"):
            with mock.patch("apps.core.sms._post", return_value={"result": {"code": 200}}) as post:
                self.assertTrue(sms.send_text("09123456789", text, "price_change"))
            url, data, headers = post.call_args.args
            self.assertTrue(url.endswith("/sms/send/simple"))
            self.assertEqual((data["receptor"], data["linenumber"], headers["apikey"]), ("09123456789", "3000", "key"))
            with mock.patch("apps.core.sms._post", side_effect=OSError("timeout")):
                self.assertFalse(sms.send_text("09123456789", text, "price_change"))
        self.assertEqual(list(SmsLog.objects.order_by("id").values_list("ok", flat=True)), [True, False])

    def test_only_admin_reads_the_sms_log(self):
        from apps.core.models import SmsLog

        SmsLog.objects.create(kind="price_change", mobile="09123456789", text="x", ok=False, detail="err")
        self.assertEqual(self.client_for(self.samt).get("/api/sms-log/").status_code, 403)
        r = self.client_for(self.admin).get("/api/sms-log/", {"ok": "false"})
        self.assertEqual((r.status_code, r.data["failed"], len(r.data["results"])), (200, 1, 1))


class ServiceTariffTests(Base):
    """کالای خدماتی: به‌جای حداکثر قیمت، نرخ‌نامه‌ای از خدمات دارد."""

    def setUp(self):
        self.svc = Product.objects.create(union=self.union, name="تعویض روغن", unit="piece", is_service=True)
        self.rows = [{"title": "تعویض روغن سواری", "price": 800_000}, {"title": "تعویض فیلتر", "price": 500_000}]

    def put(self, user, product=None, items=None):
        return self.client_for(user).put(
            f"/api/products/{(product or self.svc).pk}/tariffs/", {"items": items or self.rows}, format="json"
        )

    def test_union_replaces_its_tariff_and_numbers_rows(self):
        r = self.put(self.uni)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([(t["order"], t["title"], t["price"]) for t in r.data],
                         [(1, "تعویض روغن سواری", 800_000), (2, "تعویض فیلتر", 500_000)])
        r = self.put(self.uni, items=[{"title": "فقط یک ردیف", "price": 1}])
        self.assertEqual(len(r.data), 1)
        self.svc.refresh_from_db()
        self.assertIsNotNone(self.svc.price_changed_at)

    def test_invalid_rows_and_non_service_rejected(self):
        self.assertEqual(self.put(self.uni, items=[{"title": "", "price": 5}]).status_code, 400)
        self.assertEqual(self.put(self.uni, items=[{"title": "x", "price": "abc"}]).status_code, 400)
        self.assertEqual(self.put(self.uni, product=self.product).status_code, 400)
        self.assertEqual(self.client_for(self.uni).post(f"/api/products/{self.svc.pk}/set_price/", {"price": 5}).status_code, 400)

    def test_other_union_and_citizen_cannot_edit(self):
        self.assertEqual(self.put(self.uni2).status_code, 404)
        self.assertEqual(self.put(self.citizen).status_code, 403)

    def test_public_listing_and_detail(self):
        self.assertNotIn(self.svc.pk, [p["id"] for p in self.client_for(self.citizen).get("/api/public/products/").data["results"]])
        self.put(self.uni)
        res = APIClient().get("/api/public/products/").data["results"]
        card = next(p for p in res if p["id"] == self.svc.pk)
        self.assertTrue(card["is_service"])
        d = APIClient().get(f"/api/public/products/{self.svc.pk}/").data
        self.assertEqual((d["is_service"], len(d["tariffs"]), d["tariff_from"], d["offers"]), (True, 2, 500_000, []))

    def test_service_not_in_store_catalog_and_command_seeds_it(self):
        from django.core.management import call_command

        cat = self.client_for(self.stores[0].owner).get("/api/store/catalog/").data["items"]
        self.assertNotIn(self.svc.pk, [i["product"] for i in cat])
        union = Union.objects.create(chamber=self.chamber, name="اتحادیه تعمیرکاران اتومبیل")
        call_command("seed_service_tariffs")
        call_command("seed_service_tariffs")  # اجرای دوباره، تکراری نمی‌سازد
        p = Product.objects.get(union=union, name="تعویض روغن")
        self.assertTrue(p.is_service)
        self.assertEqual(p.tariffs.count(), 26)
        self.assertEqual(p.tariffs.get(order=26).price, 9_000_000)


class PriceSmsTemplateTests(Base):
    def test_price_change_uses_ghasedak_template_when_configured(self):
        from unittest import mock

        from django.test import override_settings

        from apps.core import sms
        from apps.core.models import SmsLog

        with override_settings(SMS_BACKEND="ghasedak", GHASEDAK_API_KEY="key", GHASEDAK_PRICE_TEMPLATE="nazerPrice"):
            with mock.patch("apps.core.sms._post", return_value={"result": {"code": 200}}) as post:
                self.assertTrue(sms.send_price_change("09123456789", "فروشگاه\nشهروند", "سیب زمینی", "65,000"))
            url, data, headers = post.call_args.args
            self.assertTrue(url.endswith("/verification/send/simple"))
            self.assertEqual((data["template"], data["param1"], data["param2"], data["param3"]),
                             ("nazerPrice", "فروشگاه شهروند", "سیب زمینی", "65,000"))
        log = SmsLog.objects.get()
        self.assertTrue(log.ok)
        self.assertIn("65,000 تومان", log.text)


class FeaturedShopTests(Base):
    """فروشگاه ویژه: کالای بدون تایید صمت، موجودی/سقف خرید، بسته پیشنهادی، کیف پول و پرداخت."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.shop.models import ShopProduct

        cls.owner = User.objects.create_user("09125550000", role=Role.STORE)
        cls.fstore = Store.objects.create(owner=cls.owner, name="ویژه", address="همدان", status=Store.Status.ACTIVE,
                                          is_featured=True)
        mk = lambda name, price, **kw: ShopProduct.objects.create(  # noqa: E731
            store=cls.fstore, name=name, price=price, old_price=kw.pop("old", price * 2), status="approved", **kw)
        cls.rice = mk("برنج", 1_000_000, stock=10, per_user_limit=3, order=2)
        cls.oil = mk("روغن", 500_000, stock=5, order=1)
        cls.buyer = User.objects.create_user("09126660000", first_name="علی", last_name="رضایی")

    def order(self, user=None, items=None, bundles=None, **extra):
        body = {"items": items if items is not None else [{"product": self.rice.pk, "quantity": 1}],
                "bundles": bundles or [], "delivery": "delivery", "address": "همدان، بلوار", "lat": "34.8", "lng": "48.5",
                "payment_method": "online", **extra}
        return self.client_for(user or self.buyer).post(f"/api/public/stores/{self.fstore.pk}/order/", body, format="json")

    def test_only_admin_defines_featured_store_without_union(self):
        body = {"name": "ویژه ۲", "address": "همدان", "is_featured": True, "owner_mobile": "09127770000"}
        self.assertEqual(self.client_for(self.uni).post("/api/stores/", body, format="json").status_code, 400)
        r = self.client_for(self.admin).post("/api/stores/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_featured"])
        bad = self.client_for(self.admin).post("/api/stores/", {**body, "owner_mobile": "09127770001", "union": self.union.pk},
                                               format="json")
        self.assertEqual(bad.status_code, 400)

    def test_store_owner_cannot_make_own_store_featured(self):
        r = self.client_for(self.stores[0].owner).patch("/api/my-store/", {"is_featured": True}, format="json")
        self.assertFalse(Store.objects.get(pk=self.stores[0].pk).is_featured, r.data)

    def test_products_auto_approved_and_stock_hidden_from_customers(self):
        c = self.client_for(self.owner)
        r = c.post("/api/shop-products/", {"name": "شکر", "price": 100_000, "old_price": 200_000, "unit": "kg", "stock": 7,
                                           "per_user_limit": 2, "is_special": True}, format="json")
        self.assertEqual((r.status_code, r.data["status"], r.data["stock"]), (201, "approved", 7))
        pub = APIClient().get(f"/api/public/stores/{self.fstore.pk}/shop/").data
        self.assertTrue(pub)
        self.assertNotIn("stock", pub[0])
        self.assertIn("per_user_limit", pub[0])
        self.assertEqual(APIClient().get("/api/public/featured-store/").data["id"], self.fstore.pk)

    def test_stock_limit_and_sold_out(self):
        self.assertEqual(self.order(items=[{"product": self.oil.pk, "quantity": 5}]).status_code, 201)
        self.oil.refresh_from_db()
        self.assertEqual((self.oil.stock, self.oil.sold_out), (0, True))
        r = self.order(items=[{"product": self.oil.pk, "quantity": 1}])
        self.assertEqual(r.status_code, 400)
        self.assertTrue(APIClient().get(f"/api/public/stores/{self.fstore.pk}/shop/").data[0]["sold_out"] is True)

    def test_per_user_limit_counts_previous_orders_and_cancel_frees_it(self):
        first = self.order(items=[{"product": self.rice.pk, "quantity": 2}])
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.order(items=[{"product": self.rice.pk, "quantity": 2}]).status_code, 400)
        other = User.objects.create_user("09126660001")
        self.assertEqual(self.order(user=other, items=[{"product": self.rice.pk, "quantity": 3}]).status_code, 201)
        self.client_for(self.buyer).post(f"/api/public/orders/{first.data['code']}/cancel/")
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock, 10 - 3)            # سفارش لغوشده موجودی را برگرداند
        self.assertEqual(self.order(items=[{"product": self.rice.pk, "quantity": 3}]).status_code, 201)

    def test_bundle_pricing_savings_and_stock(self):
        c = self.client_for(self.owner)
        r = c.post("/api/shop-bundles/", {"title": "بسته", "price": 1_300_000,
                                          "items": [{"product": self.rice.pk, "quantity": 1}, {"product": self.oil.pk, "quantity": 1}]},
                   format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["items_total"], r.data["discount_percent"]), (1_500_000, 13))
        bundles = APIClient().get(f"/api/public/stores/{self.fstore.pk}/bundles/").data
        self.assertEqual(len(bundles), 1)
        o = self.order(items=[], bundles=[{"bundle": r.data["id"], "quantity": 2}])
        self.assertEqual(o.status_code, 201, o.data)
        self.assertEqual((o.data["total"], o.data["discount"]), (2_600_000, 400_000))
        self.assertEqual(o.data["savings"], o.data["list_total"] - 2_600_000)
        self.assertEqual({i["bundle_name"] for i in o.data["items"]}, {"بسته"})
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock, 8)

    def test_bundle_from_another_store_rejected(self):
        c = self.client_for(self.owner)
        other_product = self.stores[0].shop_products.create(name="x", price=1, status="approved")
        r = c.post("/api/shop-bundles/", {"title": "b", "price": 1, "items": [{"product": other_product.pk}]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_wallet_payment_refund_and_admin_credit(self):
        from apps.shop import wallet

        from apps.shop.models import ShopProduct

        shop = self.stores[0]
        item = ShopProduct.objects.create(store=shop, name="عسل", price=1_000_000, status="approved")

        def buy(**kw):
            return self.client_for(self.buyer).post(
                f"/api/public/stores/{shop.pk}/order/",
                {"items": [{"product": item.pk, "quantity": 1}], "payment_method": "wallet", **kw}, format="json")

        self.assertEqual(buy().status_code, 400)                                      # موجودی ندارد
        self.assertEqual(self.client_for(self.citizen).post("/api/wallet/admin-credit/", {"mobile": "09126660000", "amount": 5}, format="json").status_code, 403)
        r = self.client_for(self.admin).post("/api/wallet/admin-credit/", {"mobile": "09126660000", "amount": 500_000}, format="json")
        self.assertEqual(r.data["balance"], 5_000_000)
        o = buy()
        self.assertEqual((o.status_code, o.data["payment_status"], o.data["status"]), (201, "paid", "new"))
        self.assertEqual(wallet.get_wallet(self.buyer).balance, 4_000_000)
        self.client_for(self.buyer).post(f"/api/public/orders/{o.data['code']}/cancel/")
        self.assertEqual(wallet.get_wallet(self.buyer).balance, 5_000_000)           # بازگشت وجه
        w = self.client_for(self.buyer).get("/api/wallet/").data
        self.assertEqual([t["kind"] for t in w["txs"]], ["refund", "order", "admin"])

    def test_online_payment_flow_and_failure_releases_stock(self):
        o = self.order(items=[{"product": self.oil.pk, "quantity": 2}], payment_method="online")
        self.assertEqual((o.status_code, o.data["status"]), (201, "awaiting_payment"))
        self.assertIn("/api/public/payments/callback/", o.data["payment_url"])
        # هنوز در کارتابل فروشگاه نیست
        self.assertEqual(self.client_for(self.owner).get("/api/orders/").data["count"], 0)
        cb = APIClient().get(o.data["payment_url"].split("testserver")[1])
        self.assertEqual(cb.status_code, 302)
        self.assertIn("pay=ok", cb["Location"])
        self.assertEqual(self.client_for(self.owner).get("/api/orders/").data["count"], 1)
        mine = self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]
        self.assertEqual((mine["status"], mine["payment_status"]), ("new", "paid"))
        # بازگشت دوباره از درگاه اثر دوباره ندارد
        APIClient().get(o.data["payment_url"].split("testserver")[1])
        self.assertEqual(self.client_for(self.owner).get("/api/orders/").data["count"], 1)
        # پرداخت ناموفق: سفارش لغو و موجودی آزاد می‌شود
        before = self.oil.__class__.objects.get(pk=self.oil.pk).stock
        o2 = self.order(items=[{"product": self.oil.pk, "quantity": 1}], payment_method="online")
        auth = o2.data["payment_url"].split("Authority=")[1].split("&")[0]
        APIClient().get(f"/api/public/payments/callback/?Authority={auth}&Status=NOK")
        self.assertEqual(self.oil.__class__.objects.get(pk=self.oil.pk).stock, before)
        self.assertEqual(self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]["status"], "canceled")

    def test_unpaid_online_orders_expire_and_free_stock(self):
        from datetime import timedelta

        from apps.shop.orders import Order

        o = self.order(items=[{"product": self.oil.pk, "quantity": 5}], payment_method="online")
        Order.objects.filter(code=o.data["code"]).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.order(user=User.objects.create_user("09126660002"),
                                    items=[{"product": self.oil.pk, "quantity": 5}]).status_code, 201)

    def test_wallet_topup_via_gateway(self):
        r = self.client_for(self.buyer).post("/api/wallet/topup/", {"amount": 100_000}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client_for(self.buyer).post("/api/wallet/topup/", {"amount": 10}, format="json").status_code, 400)
        cb = APIClient().get(r.data["payment_url"].split("testserver")[1])
        self.assertIn("wallet=ok", cb["Location"])
        self.assertEqual(self.client_for(self.buyer).get("/api/wallet/").data["balance"], 1_000_000)

    def test_saved_addresses_and_delivery_snapshot(self):
        c = self.client_for(self.buyer)
        a = c.post("/api/my-addresses/", {"title": "خانه", "address": "همدان، بلوار", "lat": "34.800000", "lng": "48.510000"}, format="json")
        self.assertEqual((a.status_code, a.data["is_default"]), (201, True))
        self.assertEqual(c.post("/api/my-addresses/", {"title": "کار", "address": "x"}, format="json").data["is_default"], False)
        self.assertEqual(self.client_for(self.citizen).patch(f"/api/my-addresses/{a.data['id']}/", {"title": "z"}, format="json").status_code, 404)
        no_addr = self.order(delivery="delivery", address="")
        self.assertEqual(no_addr.status_code, 400)
        o = self.order(delivery="delivery", address_id=a.data["id"])
        self.assertEqual((o.status_code, o.data["address"], o.data["lat"]), (201, "همدان، بلوار", "34.800000"))
        self.assertEqual(c.delete(f"/api/my-addresses/{a.data['id']}/").status_code, 204)
        self.assertTrue(c.get("/api/my-addresses/").data[0]["is_default"])      # پیش‌فرض به نشانی بعدی رفت

    def test_seed_command(self):
        from django.core.management import call_command

        from apps.shop.models import ShopProduct

        ShopProduct.objects.filter(store=self.fstore).delete()
        call_command("seed_featured_store", mobile="09125550000")
        self.assertEqual(ShopProduct.objects.filter(store=self.fstore).count(), 8)
        self.assertEqual(self.fstore.bundles.get().items.count(), 3)

    def test_multipart_bundle_with_json_items_and_unapproved_not_orderable(self):
        import json

        c = self.client_for(self.owner)
        r = c.post("/api/shop-bundles/", {"title": "ب", "price": 1000, "is_active": "true",
                                          "items": json.dumps([{"product": self.rice.pk, "quantity": 2}])}, format="multipart")
        self.assertEqual((r.status_code, r.data["items"][0]["quantity"]), (201, 2), r.data)
        self.rice.status = "pending"
        self.rice.save()
        self.assertEqual(self.order().status_code, 400)           # کالای تاییدنشده قابل سفارش نیست
        self.assertEqual(APIClient().get(f"/api/public/stores/{self.fstore.pk}/bundles/").data, [])

    def test_featured_store_accepts_only_online_payment_and_courier_delivery(self):
        for extra in ({"payment_method": "cash"}, {"payment_method": "wallet"}, {"delivery": "pickup"}):
            self.assertEqual(self.order(**extra).status_code, 400, extra)
        self.assertEqual(self.order().status_code, 201)

    def test_featured_courier_delivery_requires_map_location(self):
        r = self.order(lat=None, lng=None)
        self.assertEqual(r.status_code, 400)
        self.assertIn("address", r.data)
        self.assertEqual(self.order().status_code, 201)


class CourierTests(Base):
    """مدیریت پیک: تعریف پیک، ارسال لیست سفارش‌ها و گردش تحویل در اپلیکیشن پیک."""

    def setUp(self):
        from apps.shop.models import ShopProduct

        self.store = self.stores[0]
        self.owner = self.store.owner
        self.p = ShopProduct.objects.create(store=self.store, name="عسل", price=500_000, status="approved")
        self.mgr = self.client_for(self.owner)

    def make_courier(self, mobile="09128880001"):
        r = self.mgr.post("/api/couriers/", {"mobile": mobile, "first_name": "رضا", "last_name": "پیک"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"], User.objects.get(mobile=mobile)

    def order(self, delivery="delivery", method="cash", store=None):
        store = store or self.store
        r = self.client_for(self.citizen).post(
            f"/api/public/stores/{store.pk}/order/",
            {"items": [{"product": self.p.pk, "quantity": 2}], "delivery": delivery, "address": "همدان، بلوار",
             "lat": "34.8", "lng": "48.5", "payment_method": method, "customer_name": "علی"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def move(self, oid, *statuses):
        for st in statuses:
            self.assertEqual(self.mgr.post(f"/api/orders/{oid}/transition/", {"status": st}).status_code, 200)

    def test_manager_adds_courier_and_rules(self):
        cid, user = self.make_courier()
        self.assertTrue(self.client_for(user).get("/api/auth/me/").data["is_courier"])
        self.assertEqual(self.mgr.post("/api/couriers/", {"mobile": "09128880001"}, format="json").status_code, 400)  # تکراری
        self.assertEqual(self.mgr.post("/api/couriers/", {"mobile": self.uni.mobile}, format="json").status_code, 400)  # کاربر سازمانی
        self.assertEqual(self.client_for(self.stores[1].owner).get("/api/couriers/").data, [])
        self.assertEqual(self.client_for(self.citizen).get("/api/couriers/").status_code, 403)
        self.assertEqual(len(self.mgr.get("/api/couriers/").data), 1)

    def test_assign_list_and_full_delivery_flow(self):
        cid, cuser = self.make_courier()
        o1, o2 = self.order(), self.order()
        pickup_order = self.order(delivery="pickup")
        self.move(o1, "confirmed")
        # سفارش «ثبت‌شده» و سفارش حضوری پیک نمی‌گیرند
        self.assertEqual(self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [o1, o2]}, format="json").status_code, 400)
        self.move(o2, "confirmed")
        self.move(pickup_order, "confirmed")
        self.assertEqual(self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [pickup_order]}, format="json").status_code, 400)
        r = self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [o1, o2]}, format="json")
        self.assertEqual((r.status_code, r.data["assigned"]), (200, 2))
        self.assertTrue(cuser.notifications.filter(title__contains="سفارش جدید").exists())
        self.assertEqual(self.mgr.get("/api/couriers/").data[0]["to_deliver"], 2)

        c = self.client_for(cuser)
        mine = c.get("/api/courier/orders/").data
        self.assertEqual(len(mine), 2)
        self.assertEqual((mine[0]["cash_due"], mine[0]["address"], mine[0]["lat"]), (1_000_000, "همدان، بلوار", "34.800000"))
        # تا «آماده تحویل» نشده تحویل‌گرفتن ممکن نیست
        self.assertEqual(c.post(f"/api/courier/orders/{o1}/pickup/").status_code, 400)
        self.move(o1, "ready")
        self.assertEqual(c.post(f"/api/courier/orders/{o1}/deliver/").status_code, 400)       # قبل از تحویل‌گرفتن
        r = c.post(f"/api/courier/orders/{o1}/pickup/")
        self.assertEqual((r.status_code, r.data["status"]), (200, "out_for_delivery"))
        self.assertTrue(self.citizen.notifications.filter(title__contains="در مسیر").exists())
        r = c.post(f"/api/courier/orders/{o1}/deliver/")
        self.assertEqual((r.data["status"], r.data["cash_due"]), ("delivered", 0))
        mine_order = self.client_for(self.citizen).get("/api/public/orders/mine/").data
        done = next(o for o in mine_order if o["id"] == o1)
        self.assertEqual((done["payment_status"], done["courier_name"]), ("paid", "رضا پیک"))
        self.assertEqual(len(c.get("/api/courier/orders/", {"scope": "done"}).data), 1)
        self.assertEqual(len(c.get("/api/courier/orders/").data), 1)

    def test_failed_delivery_returns_to_store(self):
        cid, cuser = self.make_courier()
        oid = self.order()
        self.move(oid, "confirmed", "ready")
        self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [oid]}, format="json")
        c = self.client_for(cuser)
        c.post(f"/api/courier/orders/{oid}/pickup/")
        self.assertEqual(c.post(f"/api/courier/orders/{oid}/fail/", {}).status_code, 400)       # دلیل لازم است
        r = c.post(f"/api/courier/orders/{oid}/fail/", {"reason": "مشتری پاسخ نداد"})
        self.assertEqual((r.status_code, r.data["status"]), (200, "ready"))
        self.assertEqual(c.get("/api/courier/orders/").data, [])
        self.assertTrue(self.owner.notifications.filter(title__contains="ناموفق").exists())

    def test_isolation_between_couriers_and_stores(self):
        cid, cuser = self.make_courier()
        oid = self.order()
        self.move(oid, "confirmed", "ready")
        self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [oid]}, format="json")
        other_id, other = self.make_courier_for_other_store()
        self.assertEqual(self.client_for(other).post(f"/api/courier/orders/{oid}/pickup/").status_code, 400)
        self.assertEqual(self.client_for(self.citizen).get("/api/courier/orders/").status_code, 403)
        # مدیر فروشگاه دیگر نمی‌تواند سفارش این فروشگاه را به پیک خودش بسپارد
        r = self.client_for(self.stores[1].owner).post("/api/orders/assign/", {"courier": other_id, "orders": [oid]}, format="json")
        self.assertEqual(r.status_code, 400)

    def make_courier_for_other_store(self):
        r = self.client_for(self.stores[1].owner).post("/api/couriers/", {"mobile": "09128880002"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"], User.objects.get(mobile="09128880002")

    def test_deactivate_rules_and_cancel_notifies_courier(self):
        cid, cuser = self.make_courier()
        o1, o2 = self.order(), self.order()
        self.move(o1, "confirmed", "ready")
        self.move(o2, "confirmed")
        self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [o1, o2]}, format="json")
        self.client_for(cuser).post(f"/api/courier/orders/{o1}/pickup/")
        self.assertEqual(self.mgr.delete(f"/api/couriers/{cid}/").status_code, 400)         # سفارش در مسیر دارد
        self.move(o2, "canceled")
        self.assertTrue(cuser.notifications.filter(title__contains="لغو شد").exists())
        self.client_for(cuser).post(f"/api/courier/orders/{o1}/deliver/")
        self.assertEqual(self.mgr.delete(f"/api/couriers/{cid}/").status_code, 204)
        self.assertEqual(self.client_for(cuser).get("/api/courier/orders/").status_code, 403)  # دیگر پیک فعال نیست
        # سفارش بعدی بدون پیک می‌ماند و دوباره قابل ارسال به پیک دیگری است
        o3 = self.order()
        self.move(o3, "confirmed")
        cid2, _ = self.make_courier("09128880003")
        self.assertEqual(self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [o3]}, format="json").status_code, 400)
        self.assertEqual(self.mgr.post("/api/orders/assign/", {"courier": cid2, "orders": [o3]}, format="json").status_code, 200)
        self.assertEqual(self.mgr.post("/api/orders/assign/", {"courier": None, "orders": [o3]}, format="json").status_code, 200)
        self.assertIsNone(self.client_for(self.citizen).get("/api/public/orders/mine/").data[0]["courier"])


class ErpTests(Base):
    """انبارداری، حسابداری، فاکتور و درگاه اختصاصی فروشگاه ویژه."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.shop.models import ShopProduct

        cls.owner = User.objects.create_user("09125559999", role=Role.STORE)
        cls.fs = Store.objects.create(owner=cls.owner, name="ویژه", address="همدان", status=Store.Status.ACTIVE, is_featured=True)
        cls.rice = ShopProduct.objects.create(store=cls.fs, name="برنج", price=1_000_000, old_price=1_200_000, status="approved")
        cls.oil = ShopProduct.objects.create(store=cls.fs, name="روغن", price=500_000, status="approved")
        cls.buyer = User.objects.create_user("09126667777", first_name="علی", last_name="رضایی")

    def setUp(self):
        self.mgr = self.client_for(self.owner)

    def supplier(self):
        r = self.mgr.post("/api/erp/suppliers/", {"name": "پخش مرکزی", "phone": "081"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def buy(self, sid, items, **extra):
        return self.mgr.post("/api/erp/purchases/", {"supplier": sid, "date": "2026-10-01", "items": items, **extra}, format="json")

    def order(self, product=None, qty=1, user=None, **extra):
        body = {"items": [{"product": (product or self.rice).pk, "quantity": qty}], "delivery": "delivery", "address": "همدان",
                "lat": "34.8", "lng": "48.5", "payment_method": "online", **extra}
        return self.client_for(user or self.buyer).post(f"/api/public/stores/{self.fs.pk}/order/", body, format="json")

    def pay(self, order):
        from apps.shop.commerce import Payment

        pay = Payment.objects.filter(order_id=order["id"]).latest("id")
        self.assertEqual(APIClient().get(f"/api/public/payments/callback/?Authority={pay.authority}&Status=OK").status_code, 302)

    def deliver(self, oid):
        for st in ("confirmed", "ready", "delivered"):
            self.assertEqual(self.mgr.post(f"/api/orders/{oid}/transition/", {"status": st}).status_code, 200, st)

    # ── دسترسی ──
    def test_only_featured_owner_can_use_erp(self):
        self.assertEqual(self.mgr.get("/api/erp/dashboard/").status_code, 200)
        self.assertEqual(self.client_for(self.stores[0].owner).get("/api/erp/dashboard/").status_code, 403)
        self.assertEqual(self.client_for(self.citizen).get("/api/erp/inventory/").status_code, 403)
        self.assertEqual(APIClient().get("/api/erp/settings/").status_code, 401)

    # ── خرید، میانگین موزون و دفتر انبار ──
    def test_purchase_updates_stock_weighted_cost_and_ledger(self):
        from apps.shop.models import ShopProduct

        sid = self.supplier()
        r = self.buy(sid, [{"product": self.rice.pk, "qty": 10, "unit_cost": 100_000}], shipping=50_000, paid=300_000)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["total"], 1_050_000)
        p = ShopProduct.objects.get(pk=self.rice.pk)
        self.assertEqual((p.stock, p.cost_price), (10, 105_000))                      # حمل در قیمت تمام‌شده تسهیم شد
        self.buy(sid, [{"product": self.rice.pk, "qty": 10, "unit_cost": 125_000}])
        p.refresh_from_db()
        self.assertEqual((p.stock, p.cost_price), (20, 115_000))                      # میانگین موزون
        mv = self.mgr.get("/api/erp/movements/", {"product": self.rice.pk}).data["results"]
        self.assertEqual([(m["kind"], m["qty"], m["balance_after"]) for m in mv], [("purchase", 10, 20), ("purchase", 10, 10)])
        sup = self.mgr.get("/api/erp/suppliers/").data[0]
        self.assertEqual((sup["purchased"], sup["paid"], sup["balance"]), (2_300_000, 300_000, 2_000_000))
        pay = self.mgr.post(f"/api/erp/suppliers/{sid}/pay/", {"amount": 1_000_000, "date": "2026-10-02"}, format="json")
        self.assertEqual((pay.status_code, pay.data["balance"]), (201, 1_000_000))
        led = self.mgr.get(f"/api/erp/suppliers/{sid}/ledger/").data
        self.assertEqual(led["balance"], 1_000_000)
        # فاکتور نامعتبر
        self.assertEqual(self.buy(sid, [{"product": self.rice.pk, "qty": 1, "unit_cost": 10}], paid=999).status_code, 400)
        self.assertEqual(self.buy(sid, []).status_code, 400)
        other = self.stores[0].shop_products.create(name="x", price=1, status="approved")
        self.assertEqual(self.buy(sid, [{"product": other.pk, "qty": 1, "unit_cost": 10}]).status_code, 400)

    def test_adjustments_damage_and_negative_guard(self):
        sid = self.supplier()
        self.buy(sid, [{"product": self.oil.pk, "qty": 20, "unit_cost": 300_000}])
        adj = lambda **kw: self.mgr.post(f"/api/erp/inventory/{self.oil.pk}/adjust/", kw, format="json")  # noqa: E731
        r = adj(mode="set", value=15, note="انبارگردانی")
        self.assertEqual((r.status_code, r.data["stock"]), (200, 15))
        self.assertEqual(adj(mode="delta", value=3, kind="damage").status_code, 400)                  # دلیل لازم است
        r = adj(mode="delta", value=3, kind="damage", note="شکسته")
        self.assertEqual(r.data["stock"], 12)                                                          # ضایعات همیشه کاهشی
        self.assertEqual(adj(mode="delta", value=-99, kind="adjust").status_code, 400)               # منفی نمی‌شود
        self.assertEqual(adj(mode="set", value=12).status_code, 400)                                   # بدون تغییر
        rows = self.mgr.get("/api/erp/inventory/", {"q": "روغن"}).data
        self.assertEqual((rows["results"][0]["stock"], rows["summary"]["cost_value"]), (12, 12 * 300_000))
        upd = self.mgr.patch(f"/api/erp/inventory/{self.oil.pk}/", {"min_stock": 20, "sku": "OIL-1", "shelf": "A2"}, format="json")
        self.assertEqual(upd.status_code, 200)
        low = self.mgr.get("/api/erp/inventory/", {"status": "low"}).data["results"]
        self.assertEqual([r["name"] for r in low], ["روغن"])

    # ── فروش: موجودی، قیمت تمام‌شده، مالیات، ارسال و شماره فاکتور ──
    def test_sale_moves_stock_snapshots_cost_and_cancel_returns_it(self):
        from apps.shop.orders import OrderItem

        sid = self.supplier()
        self.buy(sid, [{"product": self.rice.pk, "qty": 10, "unit_cost": 400_000}])
        o = self.order(qty=3).data
        item = OrderItem.objects.get(order_id=o["id"])
        self.assertEqual(item.cost_price, 400_000)
        mv = self.mgr.get("/api/erp/movements/", {"product": self.rice.pk}).data["results"]
        self.assertEqual((mv[0]["kind"], mv[0]["qty"], mv[0]["balance_after"], mv[0]["ref"]), ("sale", -3, 7, o["code"]))
        self.client_for(self.buyer).post(f"/api/public/orders/{o['code']}/cancel/")
        mv = self.mgr.get("/api/erp/movements/", {"product": self.rice.pk}).data["results"]
        self.assertEqual((mv[0]["kind"], mv[0]["qty"], mv[0]["balance_after"]), ("sale_cancel", 3, 10))

    def test_low_stock_notification_fires_once_when_crossing_threshold(self):
        sid = self.supplier()
        self.buy(sid, [{"product": self.rice.pk, "qty": 10, "unit_cost": 400_000}])
        self.mgr.patch(f"/api/erp/inventory/{self.rice.pk}/", {"min_stock": 4}, format="json")
        self.order(qty=3)                                              # ۷ باقی می‌ماند: هنوز بالای حد
        self.assertFalse(self.owner.notifications.filter(title__contains="کمبود موجودی").exists())
        self.order(qty=3, user=User.objects.create_user("09126667770"))    # ۴ باقی می‌ماند: عبور از حد
        self.order(qty=1, user=User.objects.create_user("09126667771"))    # ۳ باقی می‌ماند: اعلان دوباره نمی‌رود
        self.assertEqual(self.owner.notifications.filter(title__contains="کمبود موجودی").count(), 1)

    def test_vat_delivery_fee_invoice_numbers_and_free_shipping(self):
        r = self.mgr.patch("/api/erp/settings/", {"vat_percent": 10, "delivery_fee": 400_000, "free_delivery_over": 5_000_000,
                                                 "economic_code": "411", "invoice_prefix": "NZ"}, format="json")
        self.assertEqual((r.status_code, r.data["next_invoice"]), (200, "NZ000001"))
        o1 = self.order(qty=2).data                                    # کالا ۲٬۰۰۰٬۰۰۰ + مالیات ۲۰۰٬۰۰۰ + ارسال ۴۰۰٬۰۰۰
        self.assertEqual((o1["tax"], o1["delivery_fee"], o1["total"], o1["invoice_no"]), (200_000, 400_000, 2_600_000, "NZ000001"))
        self.assertEqual(o1["savings"], 2 * 1_200_000 - 2_000_000)      # مالیات و ارسال تخفیف حساب نمی‌شود
        o2 = self.order(qty=6, user=User.objects.create_user("09126667778")).data      # بالای سقف ارسال رایگان
        self.assertEqual((o2["delivery_fee"], o2["tax"], o2["invoice_no"]), (0, 600_000, "NZ000002"))
        self.assertEqual(self.mgr.patch("/api/erp/settings/", {"vat_percent": 50}, format="json").status_code, 400)
        self.pay(o1)                                                    # سفارش پرداخت‌نشده هنوز در کارتابل فروشگاه نیست
        inv = self.mgr.get(f"/api/orders/{o1['id']}/invoice/").data
        self.assertEqual((inv["seller"]["economic_code"], inv["seller"]["vat_percent"], inv["buyer"]["name"]), ("411", 10, "علی رضایی"))
        mine = self.client_for(self.buyer).get(f"/api/public/orders/{o1['code']}/invoice/")
        self.assertEqual((mine.status_code, mine.data["invoice_no"]), (200, "NZ000001"))
        self.assertEqual(self.client_for(self.citizen).get(f"/api/public/orders/{o1['code']}/invoice/").status_code, 404)

    # ── گزارش سود ──
    def test_profit_report_and_dashboard(self):
        from django.utils import timezone

        sid = self.supplier()
        self.buy(sid, [{"product": self.rice.pk, "qty": 20, "unit_cost": 600_000}])
        self.mgr.patch("/api/erp/settings/", {"delivery_fee": 100_000}, format="json")
        o = self.order(qty=2).data                                    # درآمد ۲٬۰۰۰٬۰۰۰ ، بهای تمام‌شده ۱٬۲۰۰٬۰۰۰ ، ارسال ۱۰۰٬۰۰۰
        self.pay(o)
        self.deliver(o["id"])
        today = str(timezone.localdate())
        self.assertEqual(self.mgr.post("/api/erp/expenses/", {"category": "packaging", "amount": 50_000, "date": today}, format="json").status_code, 201)
        self.assertEqual(self.mgr.post("/api/erp/expenses/", {"category": "rent", "amount": 0, "date": today}, format="json").status_code, 400)
        rep = self.mgr.get("/api/erp/reports/sales/", {"from": today, "to": today}).data
        t = rep["totals"]
        self.assertEqual((t["orders"], t["revenue"], t["cogs"], t["gross_profit"]), (1, 2_000_000, 1_200_000, 800_000))
        self.assertEqual((t["delivery_income"], t["expenses"], t["net_profit"]), (100_000, 50_000, 850_000))
        self.assertEqual((rep["by_product"][0]["name"], rep["by_product"][0]["margin"]), ("برنج", 40.0))
        self.assertEqual(rep["by_method"][0]["payment_method"], "online")
        dash = self.mgr.get("/api/erp/dashboard/").data
        self.assertEqual((dash["today"]["net_profit"], dash["stock_value"], dash["payables"]), (850_000, 18 * 600_000, 12_000_000))
        csv_resp = self.mgr.get("/api/erp/export/sales/", {"from": today, "to": today})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("برنج", csv_resp.content.decode("utf-8-sig"))
        self.assertEqual(self.mgr.get("/api/erp/export/inventory/").status_code, 200)
        self.assertEqual(self.mgr.get("/api/erp/export/nothing/").status_code, 400)

    # ── حساب پیک ──
    def test_courier_fee_online_toggle_stats_and_settlement(self):
        cid = self.mgr.post("/api/couriers/", {"mobile": "09128880077", "first_name": "رضا"}, format="json").data["id"]
        self.assertEqual(self.mgr.patch(f"/api/couriers/{cid}/", {"fee_per_delivery": 300_000}, format="json").data["fee_per_delivery"], 300_000)
        o = self.order().data
        self.pay(o)
        self.mgr.post(f"/api/orders/{o['id']}/transition/", {"status": "confirmed"})
        self.mgr.post(f"/api/orders/{o['id']}/transition/", {"status": "ready"})
        self.mgr.post("/api/orders/assign/", {"courier": cid, "orders": [o["id"]]}, format="json")
        cu = User.objects.get(mobile="09128880077")
        c = self.client_for(cu)
        c.post(f"/api/courier/orders/{o['id']}/pickup/")
        c.post(f"/api/courier/orders/{o['id']}/deliver/")
        st = c.get("/api/courier/stats/").data
        self.assertEqual((st["today"], st["fee_today"], st["fee_due"], st["active"]), (1, 300_000, 300_000, 0))
        self.assertEqual(c.post("/api/courier/online/", {"online": False}, format="json").data["is_online"], False)
        self.assertFalse(self.mgr.get("/api/couriers/").data[0]["is_online"])
        led = self.mgr.get(f"/api/couriers/{cid}/ledger/").data
        self.assertEqual((led["deliveries"], led["fee_due"], led["cash_on_hand"], len(led["recent"])), (1, 300_000, 0, 1))
        self.assertEqual(self.mgr.post(f"/api/couriers/{cid}/settle/", {"kind": "fee", "amount": 400_000}, format="json").status_code, 400)
        self.assertEqual(self.mgr.post(f"/api/couriers/{cid}/settle/", {"kind": "cash", "amount": 1}, format="json").status_code, 400)
        r = self.mgr.post(f"/api/couriers/{cid}/settle/", {"kind": "fee", "amount": 300_000, "note": "نقدی"}, format="json")
        self.assertEqual((r.status_code, r.data["fee_due"]), (201, 0))

    def test_courier_cash_on_hand_for_cash_orders(self):
        from apps.shop.orders import Order

        cid = self.mgr.post("/api/couriers/", {"mobile": "09128880078"}, format="json").data["id"]
        o = self.order().data
        Order.objects.filter(pk=o["id"]).update(payment_method="cash", status="ready", courier_id=cid)
        c = self.client_for(User.objects.get(mobile="09128880078"))
        c.post(f"/api/courier/orders/{o['id']}/pickup/")
        c.post(f"/api/courier/orders/{o['id']}/deliver/")
        led = self.mgr.get(f"/api/couriers/{cid}/ledger/").data
        self.assertEqual((led["cash_collected"], led["cash_on_hand"]), (1_000_000, 1_000_000))
        self.assertEqual(self.mgr.post(f"/api/couriers/{cid}/settle/", {"kind": "cash", "amount": 1_000_000}, format="json").data["cash_on_hand"], 0)

    # ── درگاه اختصاصی فروشگاه ──
    def test_store_own_gateway_is_used_for_its_orders(self):
        from unittest import mock

        from apps.shop.commerce import Payment

        bad = self.mgr.patch("/api/erp/settings/", {"gateway_active": True}, format="json")
        self.assertEqual(bad.status_code, 400)                                    # بدون نوع درگاه و کد پذیرنده فعال نمی‌شود
        r = self.mgr.patch("/api/erp/settings/", {"gateway_provider": "zibal", "gateway_merchant": "MERCH1", "gateway_active": True}, format="json")
        self.assertEqual((r.status_code, r.data["own_gateway"]), (200, True))
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 100, "trackId": 4455}) as post:
            o = self.order().data
        self.assertEqual(o["payment_url"], "https://gateway.zibal.ir/start/4455")
        self.assertEqual(post.call_args.args[1]["merchant"], "MERCH1")
        pay = Payment.objects.get(order_id=o["id"])
        self.assertEqual((pay.gateway, pay.store_id, pay.authority), ("zibal", self.fs.pk, "4455"))
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 100, "amount": pay.amount, "refNumber": 99}) as v:
            cb = APIClient().get("/api/public/payments/callback/?trackId=4455&success=1&status=2")
        self.assertIn("pay=ok", cb["Location"])
        self.assertEqual(v.call_args.args[1], {"merchant": "MERCH1", "trackId": 4455})
        self.assertEqual(self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]["payment_status"], "paid")
        # شارژ کیف پول همیشه با درگاه سامانه است نه درگاه فروشگاه
        w = self.client_for(self.buyer).post("/api/wallet/topup/", {"amount": 100_000}, format="json")
        self.assertIn("Authority=MOCK", w.data["payment_url"])
        # با غیرفعال‌شدن درگاه اختصاصی، پرداخت به درگاه سامانه برمی‌گردد
        self.mgr.patch("/api/erp/settings/", {"gateway_active": False}, format="json")
        self.assertIn("Authority=MOCK", self.order(user=User.objects.create_user("09126667779")).data["payment_url"])

    def test_zarinpal_own_gateway_failure_is_reported(self):
        from unittest import mock

        self.mgr.patch("/api/erp/settings/", {"gateway_provider": "zarinpal", "gateway_merchant": "Z" * 36, "gateway_active": True}, format="json")
        with mock.patch("apps.shop.payments._post_json", return_value={"data": {"code": -9}}):
            r = self.order()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.mgr.get("/api/erp/inventory/").data["results"][0]["stock"], None)       # سفارش ناموفق، موجودی دست‌نخورده


class AuditHardeningTests(Base):
    """موارد امنیتی و پایداری که در بازبینی کامل پروژه پیدا و بسته شد."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.shop.models import ShopProduct

        cls.owner = User.objects.create_user("09125558888", role=Role.STORE)
        cls.fs = Store.objects.create(owner=cls.owner, name="ویژه", address="همدان", status=Store.Status.ACTIVE, is_featured=True)
        cls.p = ShopProduct.objects.create(store=cls.fs, name="برنج", price=1_000_000, status="approved", stock=20, cost_price=700_000)
        cls.buyer = User.objects.create_user("09126668888")

    def order(self, **extra):
        body = {"items": [{"product": self.p.pk, "quantity": 1}], "delivery": "delivery", "address": "همدان", "lat": "34.8",
                "lng": "48.5", "payment_method": "online", **extra}
        return self.client_for(self.buyer).post(f"/api/public/stores/{self.fs.pk}/order/", body, format="json")

    def test_mock_gateway_is_refused_on_production_like_settings(self):
        """بدون درگاه واقعی، «پرداخت موفق» نباید قابل جعل باشد (سفارش و شارژ کیف پول)."""
        from django.test import override_settings

        with override_settings(PAYMENT_ALLOW_MOCK=False, PAYMENT_BACKEND="console"):
            r = self.order()
            self.assertEqual(r.status_code, 400)
            self.assertIn("payment_method", r.data)
            w = self.client_for(self.buyer).post("/api/wallet/topup/", {"amount": 100_000}, format="json")
            self.assertEqual(w.status_code, 400)
        # سفارش ناموفق، موجودی را نگه نداشته است
        from apps.shop.models import ShopProduct

        self.assertEqual(ShopProduct.objects.get(pk=self.p.pk).stock, 20)

    def test_forged_mock_callback_cannot_pay_when_mock_disabled(self):
        from django.test import override_settings

        o = self.order().data                                       # با شبیه‌ساز (آزمون) ساخته شد
        from apps.shop.commerce import Payment

        pay = Payment.objects.get(order_id=o["id"])
        with override_settings(PAYMENT_ALLOW_MOCK=False):
            APIClient().get(f"/api/public/payments/callback/?Authority={pay.authority}&Status=OK")
        pay.refresh_from_db()
        self.assertEqual(pay.status, "failed")
        self.assertEqual(self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]["payment_status"], "unpaid")

    def test_duplicate_payment_of_same_order_is_returned_to_wallet(self):
        from apps.shop import wallet

        o = self.order().data
        from apps.shop.commerce import Payment

        first = Payment.objects.get(order_id=o["id"])
        again = self.client_for(self.buyer).post(f"/api/public/orders/{o['code']}/pay/")      # پرداخت دوم برای همان سفارش
        self.assertEqual(again.status_code, 200)
        second = Payment.objects.filter(order_id=o["id"]).exclude(pk=first.pk).get()
        for pay in (first, second):
            APIClient().get(f"/api/public/payments/callback/?Authority={pay.authority}&Status=OK")
        self.assertEqual(wallet.get_wallet(self.buyer).balance, 1_000_000)                  # یکی از دو پرداخت برگشت خورد
        APIClient().get(f"/api/public/payments/callback/?Authority={second.authority}&Status=OK")   # بازگشت دوباره اثر ندارد
        self.assertEqual(wallet.get_wallet(self.buyer).balance, 1_000_000)

    def test_malformed_order_input_returns_400_not_500(self):
        c = self.client_for(self.buyer)
        url = f"/api/public/stores/{self.fs.pk}/order/"
        base = {"delivery": "delivery", "address": "x", "lat": "34.8", "lng": "48.5", "payment_method": "online"}
        bad = [
            {**base, "items": [{"product": "abc"}]}, {**base, "items": "oops"}, {**base, "items": [5]},
            {**base, "items": [{"product": self.p.pk}], "lat": "north", "lng": "1"}, {**base, "items": [{"product": self.p.pk}], "lat": "999"},
            {**base, "items": [{"product": self.p.pk}], "delivery": "teleport"}, {**base, "items": [{"product": self.p.pk}], "address_id": "zz"},
            {**base, "items": [], "bundles": [{"bundle": "x"}]},
        ]
        for body in bad:
            self.assertEqual(c.post(url, body, format="json").status_code, 400, body)
        long = self.order(customer_name="ع" * 500, note="ن" * 5000, address="آ" * 900)
        self.assertEqual(long.status_code, 201)
        self.assertLessEqual(len(long.data["customer_name"]), 120)

    def test_tiny_prices_and_zero_limits_are_rejected(self):
        c = self.client_for(self.owner)
        r = c.post("/api/shop-products/", {"name": "رایگان", "price": 5, "unit": "piece"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/shop-products/", {"name": "محدود", "price": 5000, "unit": "piece", "per_user_limit": 0}, format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/shop-bundles/", {"title": "ب", "price": 1, "items": [{"product": self.p.pk}]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cost_price_and_stock_not_exposed_to_officials_or_public(self):
        """قیمت تمام‌شده و موجودی دقیق فقط برای مالک/مدیر کل؛ حتی مسئولان سازمانی در صفحه عمومی آن را نمی‌بینند."""
        for client in (APIClient(), self.client_for(self.uni), self.client_for(self.cham), self.client_for(self.citizen)):
            row = client.get(f"/api/public/stores/{self.fs.pk}/shop/").data[0]
            for k in ("stock", "cost_price", "min_stock", "shelf"):
                self.assertNotIn(k, row)
        mine = self.client_for(self.owner).get(f"/api/public/stores/{self.fs.pk}/shop/").data[0]
        self.assertEqual((mine["stock"], mine["cost_price"]), (20, 700_000))

    def test_erp_input_bounds_and_csv_formula_injection(self):
        from apps.shop.models import ShopProduct

        m = self.client_for(self.owner)
        huge = m.post(f"/api/erp/inventory/{self.p.pk}/adjust/", {"mode": "delta", "value": 10**12, "kind": "adjust"}, format="json")
        self.assertEqual(huge.status_code, 400)
        self.assertEqual(m.patch(f"/api/erp/inventory/{self.p.pk}/", {"cost_price": 10**30}, format="json").status_code, 400)
        sid = m.post("/api/erp/suppliers/", {"name": "پخش"}, format="json").data["id"]
        bad_items = m.post("/api/erp/purchases/", {"supplier": sid, "items": "x"}, format="json")
        self.assertEqual(bad_items.status_code, 400)
        self.assertEqual(m.post("/api/erp/purchases/", {"supplier": sid, "items": [3]}, format="json").status_code, 400)
        ShopProduct.objects.filter(pk=self.p.pk).update(name="=HYPERLINK(\"http://evil\")")
        csv_text = m.get("/api/erp/export/inventory/").content.decode("utf-8-sig")
        self.assertNotIn("\n=HYPERLINK", csv_text)
        self.assertIn("'=HYPERLINK", csv_text)
        # بازه چندساله به ۴۰۰ روز محدود می‌شود
        rep = m.get("/api/erp/reports/sales/", {"from": "2000-01-01", "to": "2026-01-01"}).data
        self.assertLessEqual(len(rep["series"]), 401)

    def test_wallet_admin_credit_has_upper_bound(self):
        a = self.client_for(self.admin)
        r = a.post("/api/wallet/admin-credit/", {"mobile": "09126668888", "amount": 10**15}, format="json")
        self.assertEqual(r.status_code, 400)

    # ───────── موارد بازبین مستقل ─────────

    def test_gateway_failure_releases_stock_and_cancels_order(self):
        from unittest import mock

        from apps.shop.models import ShopProduct
        from apps.shop.orders import Order

        inv = self.client_for(self.owner)
        inv.patch("/api/erp/settings/", {"gateway_provider": "zibal", "gateway_merchant": "REAL-MERCHANT", "gateway_active": True}, format="json")
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 102}):
            r = self.order(items=[{"product": self.p.pk, "quantity": 3}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ShopProduct.objects.get(pk=self.p.pk).stock, 20)                    # موجودی برگشت
        self.assertEqual(list(Order.objects.values_list("status", flat=True)), ["canceled"])  # سفارش معلق نماند

    def test_test_merchant_and_sandbox_rejected_on_real_system(self):
        from django.test import override_settings

        m = self.client_for(self.owner)
        with override_settings(PAYMENT_ALLOW_MOCK=False, DEBUG=False):
            r = m.patch("/api/erp/settings/", {"gateway_provider": "zibal", "gateway_merchant": "zibal", "gateway_active": True}, format="json")
            self.assertEqual(r.status_code, 400)
            r = m.patch("/api/erp/settings/", {"gateway_provider": "zarinpal", "gateway_merchant": "X" * 36, "gateway_sandbox": True,
                                              "gateway_active": True}, format="json")
            self.assertEqual(r.status_code, 400)
            ok = m.patch("/api/erp/settings/", {"gateway_provider": "zarinpal", "gateway_merchant": "X" * 36, "gateway_sandbox": False,
                                               "gateway_active": True}, format="json")
            self.assertEqual(ok.status_code, 200)

    def test_cancelled_return_url_still_trusts_gateway_verification(self):
        """Status=NOK در آدرس بازگشت قابل جعل است؛ اگر درگاه می‌گوید پرداخت شده، سفارش لغو نمی‌شود."""
        from unittest import mock

        from apps.shop.commerce import Payment

        m = self.client_for(self.owner)
        m.patch("/api/erp/settings/", {"gateway_provider": "zibal", "gateway_merchant": "REAL-MERCHANT", "gateway_active": True}, format="json")
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 100, "trackId": 777}):
            o = self.order().data
        pay = Payment.objects.get(order_id=o["id"])
        self.assertEqual((pay.merchant, pay.sandbox), ("REAL-MERCHANT", False))
        # فروشگاه وسط پرداخت تنظیمات درگاه را عوض می‌کند؛ تایید باید با اعتبار همان لحظه ثبت پرداخت انجام شود
        m.patch("/api/erp/settings/", {"gateway_merchant": "OTHER-MERCHANT"}, format="json")
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 100, "amount": pay.amount, "refNumber": 5}) as v:
            APIClient().get("/api/public/payments/callback/?trackId=777&success=0&status=3")
        self.assertEqual(v.call_args.args[1]["merchant"], "REAL-MERCHANT")
        self.assertEqual(self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]["payment_status"], "paid")

    def test_really_failed_payment_still_cancels_when_gateway_confirms_failure(self):
        from unittest import mock

        from apps.shop.commerce import Payment

        self.client_for(self.owner).patch("/api/erp/settings/", {"gateway_provider": "zibal", "gateway_merchant": "REAL", "gateway_active": True}, format="json")
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 100, "trackId": 888}):
            o = self.order().data
        with mock.patch("apps.shop.payments._post_json", return_value={"result": 202}):
            APIClient().get("/api/public/payments/callback/?trackId=888&success=0&status=3")
        self.assertEqual(Payment.objects.get(order_id=o["id"]).status, "failed")
        self.assertEqual(self.client_for(self.buyer).get("/api/public/orders/mine/").data[0]["status"], "canceled")

    def test_store_creation_cannot_take_over_existing_account_with_password(self):
        victim = User.objects.create_user("09125557771", first_name="قربانی")
        victim.set_password("victim-pass-1234")
        victim.save()
        body = {"name": "فروشگاه جعلی", "address": "همدان", "union": self.union.pk, "owner_mobile": "09125557771", "password": "attacker-pass-1"}
        r = self.client_for(self.uni).post("/api/stores/", body, format="json")
        self.assertEqual(r.status_code, 400)
        victim.refresh_from_db()
        self.assertTrue(victim.check_password("victim-pass-1234"))
        self.assertEqual(victim.role, Role.CITIZEN)
        # بدون رمز، شماره موجود پذیرفته می‌شود و نام قبلی کاربر بازنویسی نمی‌شود
        ok = self.client_for(self.uni).post("/api/stores/", {**body, "password": "", "owner_first_name": "دیگری"}, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)
        victim.refresh_from_db()
        self.assertEqual((victim.first_name, victim.role), ("قربانی", Role.STORE))

    def test_oversight_roles_do_not_see_customer_address_or_phone(self):
        from apps.shop.models import ShopProduct

        shop = self.stores[0]
        item = ShopProduct.objects.create(store=shop, name="عسل", price=500_000, status="approved")
        r = self.client_for(self.buyer).post(f"/api/public/stores/{shop.pk}/order/", {
            "items": [{"product": item.pk, "quantity": 1}], "delivery": "delivery", "address": "خیابان محرمانه ۱۲", "lat": "34.8",
            "lng": "48.5", "payment_method": "cash"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        row = self.client_for(self.uni).get("/api/orders/").data["results"][0]
        self.assertEqual((row["address"], row["lat"], row["lng"]), ("", None, None))
        self.assertIn("***", row["customer_phone"])
        mine = self.client_for(shop.owner).get("/api/orders/").data["results"][0]
        self.assertEqual((mine["address"], mine["customer_phone"]), ("خیابان محرمانه ۱۲", "09126668888"))

    def test_public_filters_with_garbage_do_not_500(self):
        c = APIClient()
        for url in ("/api/public/shop-products/?category=abc&county=xyz", "/api/public/special-offers/?county=%00",
                    f"/api/public/stores/{self.fs.pk}/shop/?category=abc"):
            self.assertEqual(c.get(url).status_code, 200, url)

    def test_long_notes_are_truncated_and_courier_inputs_validated(self):
        owner = self.client_for(self.owner)
        owner.post("/api/couriers/", {"mobile": "09125557772", "first_name": "ر" * 300, "last_name": 5}, format="json")
        cu = User.objects.get(mobile="09125557772")
        self.assertLessEqual(len(cu.first_name), 80)
        o = self.order().data
        self.assertEqual(owner.post("/api/orders/assign/", {"courier": "abc", "orders": [o["id"]]}, format="json").status_code, 400)
        self.assertEqual(owner.post("/api/orders/assign/", {"courier": 1, "orders": "xyz"}, format="json").status_code, 400)
        self.assertEqual(owner.post("/api/orders/assign/", {"courier": 1, "orders": ["a"]}, format="json").status_code, 400)
        self.assertEqual(owner.get("/api/erp/movements/?product=abc").status_code, 400)
        self.assertEqual(owner.get("/api/erp/purchases/?supplier=abc").status_code, 400)

    def test_stale_unpaid_orders_are_released_by_daily_job_and_storefront_view(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        from apps.shop.models import ShopProduct
        from apps.shop.orders import Order

        o = self.order(items=[{"product": self.p.pk, "quantity": 5}]).data
        self.assertEqual(ShopProduct.objects.get(pk=self.p.pk).stock, 15)
        Order.objects.filter(code=o["code"]).update(created_at=timezone.now() - timedelta(hours=2))
        APIClient().get(f"/api/public/stores/{self.fs.pk}/shop/")                   # مشاهده ویترین هم کافی است
        self.assertEqual(ShopProduct.objects.get(pk=self.p.pk).stock, 20)
        o2 = self.order(items=[{"product": self.p.pk, "quantity": 4}]).data
        Order.objects.filter(code=o2["code"]).update(created_at=timezone.now() - timedelta(hours=2))
        call_command("daily_jobs")
        self.assertEqual(ShopProduct.objects.get(pk=self.p.pk).stock, 20)
        self.assertEqual(Order.objects.get(code=o2["code"]).status, "canceled")

    def test_saved_address_validation(self):
        c = self.client_for(self.buyer)
        bad = {"title": "خانه", "address": "x", "lat": "34.8", "lng": "48.5"}
        self.assertEqual(c.post("/api/my-addresses/", {**bad, "receiver_phone": "abc"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/my-addresses/", {**bad, "lat": "95"}, format="json").status_code, 400)
        ok = c.post("/api/my-addresses/", {**bad, "receiver_phone": "۰۹۱۲۱۲۳۴۵۶۷"}, format="json")
        self.assertEqual((ok.status_code, ok.data["receiver_phone"]), (201, "09121234567"))

    def test_verify_action_parses_false(self):
        self.stores[0].is_verified = True
        self.stores[0].save()
        r = self.client_for(self.uni).post(f"/api/stores/{self.stores[0].pk}/verify/", {"value": "false"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.stores[0].refresh_from_db()
        self.assertFalse(self.stores[0].is_verified)
