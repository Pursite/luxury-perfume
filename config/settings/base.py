"""Shared Django settings for every runtime environment."""

from datetime import timedelta
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DB_CONNECT_TIMEOUT_SECONDS = env.int("DB_CONNECT_TIMEOUT_SECONDS", default=3)
REDIS_SOCKET_TIMEOUT_SECONDS = env.float("REDIS_SOCKET_TIMEOUT_SECONDS", default=2)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
    "rest_framework",
    "django_filters",
    "apps.lib",
    "apps.users",
    "apps.products",
    "apps.cart",
    "apps.orders",
    "apps.payments",
    "apps.notifications",
]

MIDDLEWARE = [
    "apps.lib.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en"
LANGUAGES = (
    ("en", "English"),
    ("fa", "Persian"),
)
LOCALE_PATHS = (BASE_DIR / "locale",)
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

ORDER_SHIPPING_FLAT_RATE_IRT = env("ORDER_SHIPPING_FLAT_RATE_IRT", default="350000.00")

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.lib.paginations.CustomPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("AUTH_ANON_THROTTLE_RATE", default="100/day"),
        "user": env("AUTH_USER_THROTTLE_RATE", default="1000/day"),
        "catalogue": env("PRODUCT_CATALOGUE_THROTTLE_RATE", default="120/m"),
        "token_refresh": env("TOKEN_REFRESH_THROTTLE_RATE", default="30/m"),
        "otp": env("OTP_REQUEST_THROTTLE_RATE", default="1/m"),
        "otp_ip": env(
            "OTP_REQUEST_IP_THROTTLE_RATE",
            default="10/m",
        ),
        "otp_verify": env("OTP_VERIFY_THROTTLE_RATE", default="10/m"),
        "otp_verify_ip": env(
            "OTP_VERIFY_IP_THROTTLE_RATE",
            default=env("OTP_VERIFY_THROTTLE_RATE", default="10/m"),
        ),
        "signup": env("SIGNUP_THROTTLE_RATE", default="5/hour"),
        "login": env("PASSWORD_LOGIN_THROTTLE_RATE", default="10/m"),
        "payment_initialize": env("PAYMENT_INITIALIZE_THROTTLE_RATE", default="10/m"),
        "payment_callback": env("PAYMENT_CALLBACK_THROTTLE_RATE", default="120/m"),
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CORS_ALLOW_CREDENTIALS = True

# The refresh token is persistent authentication state, but remains scoped to
# the API host and users endpoints. Production enables Secure in its settings.
REFRESH_TOKEN_COOKIE_NAME = "exon_refresh_token"  # nosec B105
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/users/"  # nosec B105
REFRESH_TOKEN_COOKIE_DOMAIN = None
REFRESH_TOKEN_COOKIE_HTTPONLY = True
REFRESH_TOKEN_COOKIE_SAMESITE = "Lax"  # nosec B105
REFRESH_TOKEN_COOKIE_SECURE = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.lib.logging.JsonFormatter"},
    },
    "filters": {
        "request_context": {"()": "apps.lib.logging.RequestContextFilter"},
    },
    "handlers": {
        "activity_stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
            "filters": ["request_context"],
        },
        "system_stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "loggers": {
        "django": {
            "handlers": ["system_stderr"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["system_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["system_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "system": {
            "handlers": ["system_stderr"],
            "level": "ERROR",
            "propagate": False,
        },
        "security": {
            "handlers": ["system_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "activity": {
            "handlers": ["activity_stdout"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def redis_cache(location, *, ignore_exceptions=False):
    """Build a Redis cache configuration while preserving cache failure policy."""
    options = {
        "CLIENT_CLASS": "django_redis.client.DefaultClient",
        "SOCKET_CONNECT_TIMEOUT": REDIS_SOCKET_TIMEOUT_SECONDS,
        "SOCKET_TIMEOUT": REDIS_SOCKET_TIMEOUT_SECONDS,
    }
    if ignore_exceptions:
        options["IGNORE_EXCEPTIONS"] = True
    return {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": location,
        "OPTIONS": options,
    }


JWT_STATE_REVOCATION_ENABLED = True


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=20)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    # This activates Simple JWT password-state revocation; it is not a credential.
    "CHECK_REVOKE_TOKEN": JWT_STATE_REVOCATION_ENABLED,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CACHE_TTL = 60 * 10
OTP_EXPIRY_SECONDS = env.int("OTP_EXPIRY_SECONDS", default=120)
OTP_VERIFICATION_MAX_ATTEMPTS = env.int("OTP_VERIFICATION_MAX_ATTEMPTS", default=5)
OTP_VERIFICATION_LOCK_SECONDS = env.int("OTP_VERIFICATION_LOCK_SECONDS", default=300)
PASSWORD_LOGIN_MAX_ATTEMPTS = env.int("PASSWORD_LOGIN_MAX_ATTEMPTS", default=5)
PASSWORD_LOGIN_LOCK_SECONDS = env.int("PASSWORD_LOGIN_LOCK_SECONDS", default=300)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES_SECONDS", default=86400)
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_BEAT_SCHEDULE = {
    "orders-sweep-expired-reservations": {
        "task": "apps.orders.tasks.sweep_expired_orders",
        "schedule": 60.0,
    },
    "payments-sweep-reconcilable": {
        "task": "apps.payments.tasks.sweep_reconcilable_payments",
        "schedule": 60.0,
    },
    "payments-sweep-pending-refunds": {
        "task": "apps.payments.tasks.sweep_pending_refunds",
        "schedule": 60.0,
    },
    "payments-scrub-audit-metadata": {
        "task": "apps.payments.tasks.scrub_expired_payment_audit_metadata",
        "schedule": 86400.0,
    },
    "notifications-sweep-due-sms-deliveries": {
        "task": "apps.notifications.tasks.sweep_due_sms_deliveries",
        "schedule": 60.0,
    },
    "notifications-scrub-expired-sms-recipients": {
        "task": "apps.notifications.tasks.scrub_expired_sms_recipients",
        "schedule": 86400.0,
    },
}

PAYMENTS_ENABLED = env.bool("PAYMENTS_ENABLED", default=False)
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="")
PAYMENT_CURRENCY = env("PAYMENT_CURRENCY", default="IRT")
PAYMENT_PUBLIC_BASE_URL = env("PAYMENT_PUBLIC_BASE_URL", default="")
PAYMENT_FRONTEND_RESULT_URL = env("PAYMENT_FRONTEND_RESULT_URL", default="")
PAYMENT_ALLOWED_REDIRECT_HOSTS = tuple(env.list("PAYMENT_ALLOWED_REDIRECT_HOSTS", default=[]))
PAYMENT_PROVIDER_CONNECT_TIMEOUT_SECONDS = env.float("PAYMENT_PROVIDER_CONNECT_TIMEOUT_SECONDS", default=3)
PAYMENT_PROVIDER_READ_TIMEOUT_SECONDS = env.float("PAYMENT_PROVIDER_READ_TIMEOUT_SECONDS", default=7)
PAYMENT_RECONCILIATION_HORIZON_HOURS = env.int("PAYMENT_RECONCILIATION_HORIZON_HOURS", default=24)
PAYMENT_TRUST_PROXY_HEADERS = env.bool("PAYMENT_TRUST_PROXY_HEADERS", default=False)
PAYMENT_TRUSTED_PROXY_CIDRS = tuple(env.list("PAYMENT_TRUSTED_PROXY_CIDRS", default=[]))
PAYMENT_AUDIT_RETENTION_DAYS = env.int("PAYMENT_AUDIT_RETENTION_DAYS", default=180)

SMS_ENABLED = env.bool("SMS_ENABLED", default=False)
SMS_PROVIDER = env("SMS_PROVIDER", default="")
SMS_CONNECT_TIMEOUT_SECONDS = env.float("SMS_CONNECT_TIMEOUT_SECONDS", default=3)
SMS_READ_TIMEOUT_SECONDS = env.float("SMS_READ_TIMEOUT_SECONDS", default=7)
SMS_OPERATION_LEASE_SECONDS = env.int("SMS_OPERATION_LEASE_SECONDS", default=30)
SMS_MAX_ATTEMPTS = env.int("SMS_MAX_ATTEMPTS", default=5)
SMS_RETRY_BASE_SECONDS = env.int("SMS_RETRY_BASE_SECONDS", default=5)
SMS_RETRY_MAX_SECONDS = env.int("SMS_RETRY_MAX_SECONDS", default=300)
SMS_RECIPIENT_RETENTION_DAYS = env.int("SMS_RECIPIENT_RETENTION_DAYS", default=180)
AUTH_USER_MODEL = "users.CustomUser"
