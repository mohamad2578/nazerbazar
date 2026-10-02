from django.contrib import admin

from .models import Chamber, County, Province, Store, Union

admin.site.register(Province, list_display=["name", "is_active"])
admin.site.register(County, list_display=["name", "province", "population"], list_filter=["province"])
admin.site.register(Chamber, list_display=["name", "county"])
admin.site.register(Union, list_display=["name", "chamber", "guild", "is_active"], list_filter=["chamber"])


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "union", "status", "is_verified", "rating_avg", "created_at"]
    list_filter = ["status", "union", "is_verified"]
    search_fields = ["name", "owner__mobile"]
    raw_id_fields = ["owner", "reviewed_by"]
