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

    def test_24h_grace_then_hidden_until_updated(self):
        s = self.stores[0]
        offer = upsert_offer(s, self.product, 900_000)
        set_official_price(self.product, 1_200_000, self.cham)
        # در مهلت: هنوز نمایش داده می‌شود ولی علامت «در انتظار به‌روزرسانی» دارد
        self.assertIn(offer.pk, visible_offers().values_list("pk", flat=True))
        offer.refresh_from_db()
        self.assertTrue(offer.is_stale)
        # پس از ۲۴ ساعت: پنهان
        Product.objects.filter(pk=self.product.pk).update(price_changed_at=timezone.now() - timedelta(hours=25))
        StoreOffer.objects.filter(pk=offer.pk).update(confirmed_at=timezone.now() - timedelta(hours=26))
        self.assertNotIn(offer.pk, visible_offers().values_list("pk", flat=True))
        # با به‌روزرسانی دوباره نمایش داده می‌شود
        upsert_offer(s, self.product, 1_100_000)
        self.assertIn(offer.pk, visible_offers().values_list("pk", flat=True))

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
        self.assertTrue(self.stores[0].owner.notifications.filter(title__contains="تغییر نرخ").exists())


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
    """با تغییر نرخ مصوب، قیمت اعلامی فروشگاه‌ها فورا برابر نرخ جدید می‌شود."""

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
        self.p1 = ShopProduct.objects.create(store=self.store, name="عسل", price=500_000, unit="piece")
        self.p2 = ShopProduct.objects.create(store=self.store, name="زعفران", price=900_000, unit="g")

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
