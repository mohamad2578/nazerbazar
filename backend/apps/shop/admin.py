from django.contrib import admin

from .models import ShopCategory, ShopProduct
from .orders import Order, OrderItem

admin.site.register(ShopCategory, list_display=["name", "order"])
admin.site.register(
    ShopProduct,
    list_display=["name", "store", "price", "is_available", "is_active"],
    list_filter=["is_active", "is_available", "category"],
    search_fields=["name", "store__name"],
    raw_id_fields=["store"],
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["code", "store", "customer_name", "total", "status", "created_at"]
    list_filter = ["status", "delivery"]
    search_fields = ["code", "customer_name", "customer_phone"]
    raw_id_fields = ["store", "customer"]
    inlines = [OrderItemInline]
