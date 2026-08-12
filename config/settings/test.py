"""Self-contained settings for the automated test suite."""

import os


os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("JWT_SIGNING_KEY", "test-only-jwt-signing-key-at-least-32-bytes")

from .base import *  # noqa: E402,F403


DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "luxury-perfume-tests-default",
    },
    "security": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "luxury-perfume-tests-security",
    },
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
