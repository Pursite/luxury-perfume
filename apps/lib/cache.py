from django.core.cache import cache
from django.conf import settings
from apps.lib.loggers import AppLogger


class RedisCacheService:
    @staticmethod
    def get(key):
        try:
            return cache.get(key)
        except Exception as e:
            AppLogger.log_system_error(f"Redis GET Error for key {key}: {str(e)}")
            return None

    @staticmethod
    def set(key, value, timeout=None):
        if timeout is None:
            timeout = settings.CACHE_TTL
        try:
            cache.set(key, value, timeout)
            return True
        except Exception as e:
            AppLogger.log_system_error(f"Redis SET Error for key {key}: {str(e)}")
            return False

    @staticmethod
    def delete(key):
        try:
            cache.delete(key)
            return True
        except Exception as e:
            AppLogger.log_system_error(f"Redis DELETE Error for key {key}: {str(e)}")
            return False

    @staticmethod
    def clear_all():
        try:
            cache.clear()
            return True
        except Exception as e:
            AppLogger.log_system_error(f"Redis CLEAR Error: {str(e)}")
            return False
