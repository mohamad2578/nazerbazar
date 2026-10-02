from django.contrib import admin

from .models import Alert, Commodity, CommodityReport

admin.site.register(Commodity, list_display=["name", "group", "unit", "basket_monthly_qty", "subsidized"], list_editable=["basket_monthly_qty"])
admin.site.register(CommodityReport, list_display=["commodity", "province", "period"], list_filter=["commodity", "province"])
admin.site.register(Alert, list_display=["title", "kind", "level", "is_resolved", "created_at"], list_filter=["kind", "level", "is_resolved"])
