"""Small framework-native health endpoints for the web process."""

from django.apps import apps
from django.core.cache import caches
from django.db import connections
from django.http import JsonResponse


_SECURITY_CACHE_HEALTH_KEY = "health:ready"


def _database_ready() -> bool:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return False
    return True


def _security_cache_ready() -> bool:
    try:
        return caches["security"].set(_SECURITY_CACHE_HEALTH_KEY, "ok", timeout=1) is not False
    except Exception:
        return False


def live(request):
    """Confirm that this Django process can handle an HTTP request."""
    return JsonResponse({"status": "ok"})


def ready(request):
    """Confirm dependencies required to serve requests safely are available."""
    database = "ok" if _database_ready() else "unavailable"
    security_cache = "ok" if _security_cache_ready() else "unavailable"
    is_ready = database == "ok" and security_cache == "ok"

    return JsonResponse(
        {
            "status": "ok" if is_ready else "unavailable",
            "database": database,
            "security_cache": security_cache,
        },
        status=200 if is_ready else 503,
    )


def startup(request):
    """Confirm Django has initialized its application registry."""
    is_started = apps.ready
    return JsonResponse(
        {"status": "ok" if is_started else "unavailable"},
        status=200 if is_started else 503,
    )
