from rest_framework.permissions import SAFE_METHODS, BasePermission


def role_permission(*roles):
    """کلاس مجوز برای نقش‌های مشخص؛ مدیر کل همیشه مجاز است."""

    class _RolePermission(BasePermission):
        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and (u.role in roles or u.role == "admin"))

    _RolePermission.__name__ = "Role_" + "_".join(roles)
    return _RolePermission


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
