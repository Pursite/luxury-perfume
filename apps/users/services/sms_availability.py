"""Shared delivery readiness for Users-owned OTP operations."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException

from apps.lib.sms.registry import get_provider


class SmsUnavailable(APIException):
    status_code = 503
    default_detail = _("SMS verification is currently unavailable.")


def sms_available():
    if not settings.SMS_ENABLED:
        return False
    try:
        provider = get_provider(settings.SMS_PROVIDER)
        return (
            callable(getattr(provider, "send_sms", None))
            and not provider.configuration_errors()
        )
    except Exception:
        return False


def ensure_sms_available():
    if not sms_available():
        raise SmsUnavailable
