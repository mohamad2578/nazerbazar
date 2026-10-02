from django.contrib import admin

from .models import ShopCategory, ShopProduct

admin.site.register(ShopCategory, list_display=["name", "order"])
admin.site.register(
    ShopProduct,
    list_display=["name", "store", "price", "is_available", "is_active"],
    list_filter=["is_active", "is_available", "category"],
    search_fields=["name", "store__name"],
    raw_id_fields=["store"],
)
