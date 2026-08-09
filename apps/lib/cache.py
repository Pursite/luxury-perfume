from django.core.cache import cache
from django.conf import settings
from apps.lib.loggers import AppLogger


class RedisCacheService:
    @staticmethod
    def get(key):
        try:
            return cache.get(key)
        except Exception:
            AppLogger.log_system_error(msg="cache.get.failed")
            return None

    @staticmethod
    def set(key, value, timeout=None):
        if timeout is None:
            timeout = settings.CACHE_TTL
        try:
            cache.set(key, value, timeout)
            return True
        except Exception:
            AppLogger.log_system_error(msg="cache.set.failed")
            return False

    @staticmethod
    def incr(key, timeout=None):
        try:
            cache.add(key, 0, timeout=timeout)
            return cache.incr(key)
        except Exception:
            AppLogger.log_system_error(msg="cache.incr.failed")
            return None

    @staticmethod
    def delete(key):
        try:
            cache.delete(key)
            return True
        except Exception:
            AppLogger.log_system_error(msg="cache.delete.failed")
            return False

    @staticmethod
    def clear_all():
        try:
            cache.clear()
            return True
        except Exception:
            AppLogger.log_system_error(msg="cache.clear.failed")
            return False
