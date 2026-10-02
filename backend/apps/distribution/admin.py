from django.contrib import admin

from .models import Allocation, AllocationShare, Quota

admin.site.register(Allocation, list_display=["title", "commodity", "province", "total_quantity", "status"])
admin.site.register(AllocationShare, list_display=["allocation", "union", "quantity"])
admin.site.register(Quota, list_display=["tracking_code", "store", "quantity", "received_quantity", "status"])
