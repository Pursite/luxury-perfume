from django.conf import settings
from django.core.checks import Error, register

from apps.lib.sms.phone import normalize_iranian_mobile
from apps.lib.sms.registry import ProviderNotRegistered, get_provider


_REQUIRED_PROVIDER_METHODS = ("send_sms", "configuration_errors")


@register()
def check_sms_settings(app_configs, **kwargs):
    if not getattr(settings, "SMS_ENABLED", False):
        return []
    errors = []
    provider = None
    try:
        provider = get_provider(getattr(settings, "SMS_PROVIDER", ""))
        if any(not callable(getattr(provider, method, None)) for method in _REQUIRED_PROVIDER_METHODS):
            raise ProviderNotRegistered
    except ProviderNotRegistered:
        errors.append(Error("SMS_PROVIDER is not registered.", id="notifications.E001"))
    if normalize_iranian_mobile(getattr(settings, "ORDER_PROCESSING_ALERT_PHONE", "")) is None:
        errors.append(Error("ORDER_PROCESSING_ALERT_PHONE must be a canonical Iranian mobile number.", id="notifications.E002"))
    numeric = (
        "SMS_CONNECT_TIMEOUT_SECONDS",
        "SMS_READ_TIMEOUT_SECONDS",
        "SMS_OPERATION_LEASE_SECONDS",
        "SMS_MAX_ATTEMPTS",
        "SMS_RETRY_BASE_SECONDS",
        "SMS_RETRY_MAX_SECONDS",
        "SMS_RECIPIENT_RETENTION_DAYS",
    )
    if any(getattr(settings, name, 0) <= 0 for name in numeric):
        errors.append(Error("SMS timeout, retry, and retention settings must be positive.", id="notifications.E003"))
    if getattr(settings, "SMS_OPERATION_LEASE_SECONDS", 0) <= (
        getattr(settings, "SMS_CONNECT_TIMEOUT_SECONDS", 0)
        + getattr(settings, "SMS_READ_TIMEOUT_SECONDS", 0)
    ):
        errors.append(Error("SMS_OPERATION_LEASE_SECONDS must exceed the provider network budget.", id="notifications.E004"))
    if getattr(settings, "SMS_RETRY_BASE_SECONDS", 0) > getattr(settings, "SMS_RETRY_MAX_SECONDS", 0):
        errors.append(Error("SMS_RETRY_BASE_SECONDS must not exceed SMS_RETRY_MAX_SECONDS.", id="notifications.E005"))
    if provider is not None:
        try:
            configuration_errors = tuple(provider.configuration_errors())
        except Exception:
            configuration_errors = ("invalid",)
        if configuration_errors:
            errors.append(Error("The configured SMS provider is invalid.", id="notifications.E006"))
    return errors
