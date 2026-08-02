"""Settings for development environments."""

from .base import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),  # noqa: F405
        "USER": env("DB_USER"),  # noqa: F405
        "PASSWORD": env("DB_PASSWORD"),  # noqa: F405
        "HOST": env("DB_HOST"),  # noqa: F405
        "PORT": env("DB_PORT"),  # noqa: F405
        "OPTIONS": {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},  # noqa: F405
    }
}

CACHES = {
    "default": redis_cache(
        env("CACHE_REDIS_URL"),  # noqa: F405
        ignore_exceptions=True,
    ),
    "security": redis_cache(env("SECURITY_REDIS_URL")),  # noqa: F405
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL")  # noqa: F405
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")  # noqa: F405

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
