"""PostgreSQL and Redis settings for explicitly marked integration tests."""

from .test import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("INTEGRATION_DB_NAME", default="wine_shop_test"),  # noqa: F405
        "USER": env("INTEGRATION_DB_USER", default="wine_shop_test"),  # noqa: F405
        "PASSWORD": env(  # noqa: F405
            "INTEGRATION_DB_PASSWORD",
            default="",
        ),
        "HOST": env("INTEGRATION_DB_HOST", default="127.0.0.1"),  # noqa: F405
        "PORT": env("INTEGRATION_DB_PORT", default="55432"),  # noqa: F405
        "OPTIONS": {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},  # noqa: F405
        "CONN_MAX_AGE": 0,
    }
}

CACHES = {
    "default": redis_cache(  # noqa: F405
        env(  # noqa: F405
            "INTEGRATION_CACHE_REDIS_URL",
            default="redis://127.0.0.1:56379/14",
        ),
    ),
    "security": redis_cache(  # noqa: F405
        env(  # noqa: F405
            "INTEGRATION_SECURITY_REDIS_URL",
            default="redis://127.0.0.1:56379/15",
        ),
    ),
}
