from django.conf import settings
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


class CookieAuthOriginPermission(permissions.BasePermission):
    """Require a trusted browser origin for refresh-cookie mutations."""

    message = "This authentication request has an invalid origin."

    def has_permission(self, request, view):
        # CORS middleware handles browser preflight before the view. Allowing
        # OPTIONS here also keeps direct DRF metadata/preflight requests safe.
        if request.method == "OPTIONS":
            return True

        origin = request.headers.get("Origin")
        if not origin:
            raise PermissionDenied(self.message)

        api_origin = f"{request.scheme}://{request.get_host()}"
        allowed_origins = set(getattr(settings, "CORS_ALLOWED_ORIGINS", ()))
        if origin == api_origin or origin in allowed_origins:
            return True

        raise PermissionDenied(self.message)
