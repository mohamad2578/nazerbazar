from django.contrib import admin

from .models import Category, OfficialPrice, Product, Review, StoreOffer

admin.site.register(Category, list_display=["name", "order"])
admin.site.register(Product, list_display=["name", "union", "current_price", "price_changed_at", "is_active"], list_filter=["union", "is_active"], search_fields=["name"])
admin.site.register(OfficialPrice, list_display=["product", "price", "previous_price", "created_at"])
admin.site.register(StoreOffer, list_display=["store", "product", "price", "confirmed_at", "is_available"], raw_id_fields=["store", "product"])
admin.site.register(Review, list_display=["store", "user", "rating", "is_visible"])
