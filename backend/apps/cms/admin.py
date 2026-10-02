from django.contrib import admin

from .models import Slide

admin.site.register(Slide, list_display=["title", "order", "is_active", "created_at"], list_editable=["order", "is_active"])
