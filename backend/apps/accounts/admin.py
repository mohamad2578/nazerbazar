from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import OTP, Notification, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["mobile", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    search_fields = ["mobile", "first_name", "last_name"]
    fieldsets = [
        (None, {"fields": ["mobile", "password"]}),
        ("مشخصات", {"fields": ["first_name", "last_name", "national_code"]}),
        ("نقش و حوزه", {"fields": ["role", "province", "chamber", "union"]}),
        ("دسترسی", {"fields": ["is_active", "is_staff", "is_superuser"]}),
    ]
    add_fieldsets = [(None, {"fields": ["mobile", "password1", "password2", "role"]})]


admin.site.register(OTP, list_display=["mobile", "created_at", "used", "attempts"])
admin.site.register(Notification, list_display=["user", "title", "is_read", "created_at"])
