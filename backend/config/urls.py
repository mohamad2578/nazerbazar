from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts import api as accounts
from apps.analytics import api as analytics
from apps.cms import api as cms
from apps.news import api as news
from apps.suppliers import api as suppliers
from apps.complaints import api as complaints
from apps.core import backup_api
from apps.distribution import api as distribution
from apps.market import api as market
from apps.market import price_api
from apps.observatory import api as observatory
from apps.orgs import api as orgs
from apps.shop import api as shop
from apps.shop import order_api as orders

router = DefaultRouter()
router.register("slides", cms.SlideViewSet, basename="slide")
router.register("news", news.NewsAdminViewSet, basename="news")
router.register("suppliers", suppliers.SupplierViewSet, basename="supplier")
router.register("notifications", accounts.NotificationViewSet, basename="notification")
router.register("users", accounts.UserViewSet, basename="user")
router.register("provinces", orgs.ProvinceViewSet, basename="province")
router.register("counties", orgs.CountyViewSet, basename="county")
router.register("chambers", orgs.ChamberViewSet, basename="chamber")
router.register("unions", orgs.UnionViewSet, basename="union")
router.register("stores", orgs.StoreViewSet, basename="store")
router.register("categories", market.CategoryViewSet, basename="category")
router.register("products", market.ProductViewSet, basename="product")
router.register("complaints", complaints.ComplaintViewSet, basename="complaint")
router.register("commodities", observatory.CommodityViewSet, basename="commodity")
router.register("commodity-reports", observatory.CommodityReportViewSet, basename="commodity-report")
router.register("alerts", observatory.AlertViewSet, basename="alert")
router.register("allocations", distribution.AllocationViewSet, basename="allocation")
router.register("shares", distribution.ShareViewSet, basename="share")
router.register("quotas", distribution.QuotaViewSet, basename="quota")
router.register("shop-categories", shop.ShopCategoryViewSet, basename="shop-category")
router.register("shop-products", shop.MyShopProductViewSet, basename="shop-product")
router.register("other-prices", shop.ShopPriceReviewViewSet, basename="other-price")
router.register("orders", orders.OrderViewSet, basename="order")
router.register("public/geo", orgs.PublicGeoViewSet, basename="public-geo")

api = [
    path("auth/otp/request/", accounts.otp_request),
    path("auth/otp/verify/", accounts.otp_verify),
    path("auth/login/", accounts.password_login),
    path("auth/register/", accounts.citizen_register),
    path("auth/me/", accounts.me),
    path("auth/token/refresh/", TokenRefreshView.as_view()),
    path("my-store/", orgs.my_store),
    path("store/catalog/", market.store_catalog),
    path("store/offers/", market.store_save_offers),
    path("store/offers/<int:product_id>/", market.store_remove_offer),
    path("public/slides/", cms.public_slides),
    path("public/news/", news.public_news),
    path("public/news/<int:pk>/", news.public_news_detail),
    path("public/suppliers/", suppliers.public_supplier_register),
    path("public/stats/", market.public_stats),
    path("public/products/", market.public_products),
    path("public/products/<int:pk>/", market.public_product_detail),
    path("public/stores/<int:pk>/", market.public_store_detail),
    path("public/stores/<int:pk>/reviews/", market.submit_review),
    path("public/stores/<int:pk>/shop/", shop.public_shop),
    path("public/shop-products/", shop.public_shop_products),
    path("store/shop-summary/", shop.my_shop_summary),
    path("public/stores/<int:pk>/order/", orders.place_order),
    path("public/orders/mine/", orders.my_orders),
    path("public/orders/<str:code>/cancel/", orders.cancel_my_order),
    path("public/map/", market.public_map),
    path("public/observatory/", observatory.public_observatory),
    path("public/subsidized/", distribution.public_subsidized),
    path("public/quota/<str:code>/", distribution.public_track_quota),
    path("public/complaints/", complaints.submit),
    path("public/complaints/mine/", complaints.my_complaints),
    path("public/complaints/track/", complaints.track),
    path("prices/pending/", price_api.pending_prices),
    path("prices/<int:pk>/review/", price_api.review_price),
    path("prices/bulk-template/", price_api.bulk_template),
    path("prices/bulk-upload/", price_api.bulk_upload),
    path("analytics/overview/", analytics.overview),
    path("analytics/trends/", analytics.trends),
    path("analytics/price-changes/", analytics.price_changes),
    path("analytics/complaints/", analytics.complaints_report),
    path("analytics/unions/", analytics.unions_report),
    path("analytics/counties/", analytics.counties_report),
    path("analytics/basket/", analytics.basket_report),
    path("analytics/distribution/", analytics.distribution_report),
    path("analytics/export/<str:name>/", analytics.export),
    path("backup/status/", backup_api.status),
    path("backup/download/", backup_api.download),
    path("backup/inspect/", backup_api.inspect),
    path("backup/restore/", backup_api.restore),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include(api)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
