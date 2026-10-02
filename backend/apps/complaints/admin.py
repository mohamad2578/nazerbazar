from django.contrib import admin

from .models import Complaint, ComplaintEvent


class EventInline(admin.TabularInline):
    model = ComplaintEvent
    extra = 0


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ["tracking_code", "kind", "status", "store", "union", "created_at"]
    list_filter = ["status", "kind", "union"]
    search_fields = ["tracking_code"]
    raw_id_fields = ["reporter", "store", "product"]
    inlines = [EventInline]
