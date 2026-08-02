"""Settings for direct local development services."""

from .base import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="wine_shop"),  # noqa: F405
        "USER": env("DB_USER", default="wine_shop"),  # noqa: F405
        "PASSWORD": env("DB_PASSWORD", default="wine_shop"),  # noqa: F405
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),  # noqa: F405
        "OPTIONS": {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},  # noqa: F405
    }
}

CACHES = {
    "default": redis_cache(
        env("CACHE_REDIS_URL", default="redis://localhost:6379/0"),  # noqa: F405
        ignore_exceptions=True,
    ),
    "security": redis_cache(
        env("SECURITY_REDIS_URL", default="redis://localhost:6379/1")  # noqa: F405
    ),
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/2")  # noqa: F405
CELERY_RESULT_BACKEND = env(  # noqa: F405
    "CELERY_RESULT_BACKEND", default="redis://localhost:6379/3"
)

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
