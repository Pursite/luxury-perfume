from rest_framework import permissions
from .loggers import AppLogger


class IsAdminOrReadOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        is_staff = bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )
        if not is_staff:
            AppLogger.log_security(
                msg=f"Unauthorized Write Attempt: {request.method}",
                user=request.user,
                path=request.path,
            )
        return is_staff


class IsAdmin(permissions.BasePermission):

    def has_permission(self, request, view):
        is_staff = bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )
        if not is_staff:
            AppLogger.log_security(
                msg=f"Unauthorized Admin-Route Access: {request.method}",
                user=request.user,
                path=request.path,
            )
        return is_staff
