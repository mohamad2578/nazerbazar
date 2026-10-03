"""تست قواعد اصلی: سقف/کف قیمت، مهلت ۲۴ ساعته، مرتب‌سازی، دسترسی سلسله‌مراتبی، شکایت و توزیع."""
from datetime import timedelta

from django.core.cache import cache
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
        set_official_price(cls.product, 1_000_000, cls.uni)

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
        set_official_price(self.product, 1_000_000, self.uni, max_discount=10)
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
        set_official_price(self.product, 1_200_000, self.uni)
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
        set_official_price(self.product, 1_000_000, self.uni)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_changed_at, changed)
        offer.refresh_from_db()
        self.assertFalse(offer.is_stale)

    def test_store_notified_on_price_change(self):
        upsert_offer(self.stores[0], self.product, 900_000)
        set_official_price(self.product, 1_100_000, self.uni)
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

    def test_union_creates_product_in_own_union(self):
        r = self.client_for(self.uni).post("/api/products/", {"name": "عدس", "unit": "kg", "initial_price": 300000})
        self.assertEqual(r.status_code, 201, r.data)
        p = Product.objects.get(pk=r.data["id"])
        self.assertEqual((p.union_id, p.current_price), (self.union.pk, 300000))

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

    def test_public_shop_hides_inactive_products(self):
        from apps.shop.models import ShopProduct

        store = self.stores[0]
        ShopProduct.objects.create(store=store, name="نمایش‌داده‌شده", price=1000)
        ShopProduct.objects.create(store=store, name="پنهان", price=2000, is_active=False)
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
        set_official_price(self.product, 1_200_000, self.uni)
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
        set_official_price(self.product, 1_000_000, self.uni)  # همان نرخ قبلی
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
