"""Fail-closed deployment checks for the disabled-by-default subsystem."""

from ipaddress import ip_network
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, register

from apps.payments.providers.registry import ProviderNotRegistered, get_provider


REQUIRED_PROVIDER_METHODS = (
    "create_payment",
    "verify_payment",
    "refund_payment",
    "lookup_payment",
    "parse_callback",
    "build_redirect_url",
)
_REDIRECT_HOST = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def _https_url(value):
    parsed = urlparse(value or "")
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _redirect_hosts_are_safe(hosts):
    return bool(hosts) and all(
        isinstance(host, str)
        and len(host) <= 253
        and _REDIRECT_HOST.fullmatch(host) is not None
        and not host.startswith("replace-")
        for host in hosts
    )


@register()
def check_payment_settings(app_configs, **kwargs):
    if not getattr(settings, "PAYMENTS_ENABLED", False):
        return []
    errors = []
    try:
        provider = get_provider(getattr(settings, "PAYMENT_PROVIDER", ""))
        if any(not callable(getattr(provider, method, None)) for method in REQUIRED_PROVIDER_METHODS):
            raise ProviderNotRegistered
    except ProviderNotRegistered:
        errors.append(Error("PAYMENT_PROVIDER is not registered.", id="payments.E001"))
    if not _https_url(getattr(settings, "PAYMENT_PUBLIC_BASE_URL", "")):
        errors.append(Error("PAYMENT_PUBLIC_BASE_URL must be HTTPS.", id="payments.E002"))
    if not _https_url(getattr(settings, "PAYMENT_FRONTEND_RESULT_URL", "")):
        errors.append(Error("PAYMENT_FRONTEND_RESULT_URL must be HTTPS.", id="payments.E003"))
    if not _redirect_hosts_are_safe(getattr(settings, "PAYMENT_ALLOWED_REDIRECT_HOSTS", ())):
        errors.append(Error("At least one redirect host is required.", id="payments.E004"))
    cidrs = getattr(settings, "PAYMENT_TRUSTED_PROXY_CIDRS", ())
    if not getattr(settings, "PAYMENT_TRUST_PROXY_HEADERS", False) or not cidrs:
        errors.append(Error("Explicit trusted proxy CIDRs are required.", id="payments.E005"))
    else:
        try:
            tuple(ip_network(cidr, strict=False) for cidr in cidrs)
        except ValueError:
            errors.append(Error("PAYMENT_TRUSTED_PROXY_CIDRS contains an invalid network.", id="payments.E006"))
    if getattr(settings, "PAYMENT_CURRENCY", "") != "IRT":
        errors.append(Error("PAYMENT_CURRENCY must be IRT in v1.", id="payments.E007"))
    numeric_settings = (
        "PAYMENT_PROVIDER_CONNECT_TIMEOUT_SECONDS",
        "PAYMENT_PROVIDER_READ_TIMEOUT_SECONDS",
        "PAYMENT_RECONCILIATION_HORIZON_HOURS",
        "PAYMENT_AUDIT_RETENTION_DAYS",
    )
    if any(getattr(settings, name, 0) <= 0 for name in numeric_settings):
        errors.append(Error("Payment timeout and retention settings must be positive.", id="payments.E008"))
    return errors
