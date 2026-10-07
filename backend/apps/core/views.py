from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .scoping import scoped

PANEL_ROLES = ("admin", "governorate", "samt", "chamber", "union", "store")


class ScopedPermission(BasePermission):
    """خواندن برای نقش‌های read_roles و نوشتن برای write_roles ویوست."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if u.role == "admin":
            return True
        roles = view.read_roles if request.method in SAFE_METHODS else view.write_roles
        action_roles = getattr(view, "action_roles", {}).get(getattr(view, "action", None))
        return u.role in (action_roles or roles)


class ScopedModelViewSet(viewsets.ModelViewSet):
    """ویوست پایه پنل‌ها: داده‌ها به حوزه کاربر محدود می‌شود و ایجاد/ویرایش خارج از حوزه رد می‌شود."""

    permission_classes = [ScopedPermission]
    read_roles = PANEL_ROLES
    write_roles = ("admin",)

    def get_queryset(self):
        qs = super().get_queryset()
        return scoped(qs, self.request.user, qs.model.SCOPE).distinct()

    def _save_in_scope(self, serializer, **extra):
        with transaction.atomic():
            instance = serializer.save(**extra)
            if not self.get_queryset().filter(pk=instance.pk).exists():
                raise PermissionDenied("خارج از حوزه دسترسی شما است.")
        return instance

    def perform_create(self, serializer):
        self._save_in_scope(serializer)

    def perform_update(self, serializer):
        self._save_in_scope(serializer)
