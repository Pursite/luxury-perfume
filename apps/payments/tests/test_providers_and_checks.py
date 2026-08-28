from decimal import Decimal

import pytest
from django.core.checks import Error
from django.test import override_settings

from apps.payments.exceptions import PaymentProviderProtocolError
from apps.payments.providers.base import irt_to_rial
from apps.payments.providers.registry import ProviderNotRegistered, get_provider, register_provider


class _Adapter:
    pass


def test_provider_registry_rejects_unknown_names_and_returns_allowlisted_adapter():
    adapter = _Adapter()
    register_provider("contract-test", adapter)

    assert get_provider("contract-test") is adapter
    with pytest.raises(ProviderNotRegistered):
        get_provider("attacker-controlled")


@pytest.mark.parametrize(
    "name",
    ("../provider", "UPPERCASE", "provider_name", "x" * 33),
)
def test_provider_registry_rejects_names_that_cannot_be_safe_route_slugs(name):
    with pytest.raises(ValueError):
        register_provider(name, _Adapter())


def test_irt_to_rial_conversion_never_rounds_fractional_rials():
    assert irt_to_rial(Decimal("125.00")) == 1250
    with pytest.raises(PaymentProviderProtocolError):
        irt_to_rial(Decimal("0.01"))


@override_settings(PAYMENTS_ENABLED=False)
def test_disabled_payments_require_no_provider_configuration():
    from apps.payments.checks import check_payment_settings

    assert check_payment_settings(None) == []


@override_settings(
    PAYMENTS_ENABLED=True,
    PAYMENT_PROVIDER="unknown-provider",
    PAYMENT_PUBLIC_BASE_URL="http://api.example.test",
    PAYMENT_FRONTEND_RESULT_URL="https://shop.example.test/payment",
    PAYMENT_ALLOWED_REDIRECT_HOSTS=(),
    PAYMENT_TRUST_PROXY_HEADERS=True,
    PAYMENT_TRUSTED_PROXY_CIDRS=(),
)
def test_enabled_payments_fail_closed_for_unsafe_or_missing_configuration():
    from apps.payments.checks import check_payment_settings

    errors = check_payment_settings(None)

    assert errors
    assert all(isinstance(error, Error) for error in errors)
    assert {error.id for error in errors} >= {
        "payments.E001",
        "payments.E002",
        "payments.E004",
        "payments.E005",
    }


@override_settings(
    PAYMENTS_ENABLED=True,
    PAYMENT_PROVIDER="incomplete-adapter",
    PAYMENT_CURRENCY="IRT",
    PAYMENT_PUBLIC_BASE_URL="https://api.example.test/path?bad=query",
    PAYMENT_FRONTEND_RESULT_URL="https://shop.example.test/result#fragment",
    PAYMENT_ALLOWED_REDIRECT_HOSTS=("gateway.example.test",),
    PAYMENT_TRUST_PROXY_HEADERS=True,
    PAYMENT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
    PAYMENT_PROVIDER_CONNECT_TIMEOUT_SECONDS=0,
)
def test_enablement_rejects_incomplete_adapter_and_noncanonical_settings():
    from apps.payments.checks import check_payment_settings

    register_provider("incomplete-adapter", object())
    errors = check_payment_settings(None)

    assert {error.id for error in errors} >= {
        "payments.E001",
        "payments.E002",
        "payments.E003",
        "payments.E008",
    }


@override_settings(
    PAYMENTS_ENABLED=True,
    PAYMENT_PROVIDER="complete-adapter",
    PAYMENT_CURRENCY="IRT",
    PAYMENT_PUBLIC_BASE_URL="https://api.example.test",
    PAYMENT_FRONTEND_RESULT_URL="https://shop.example.test/result",
    PAYMENT_ALLOWED_REDIRECT_HOSTS=("https://gateway.example.test", "replace-with-provider-host"),
    PAYMENT_TRUST_PROXY_HEADERS=True,
    PAYMENT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
)
def test_enablement_rejects_non_host_redirect_allowlist_entries():
    from apps.payments.checks import check_payment_settings

    adapter = type(
        "CompleteAdapter",
        (),
        {method: lambda self, **kwargs: None for method in (
            "create_payment", "verify_payment", "refund_payment", "lookup_payment",
            "parse_callback", "build_redirect_url",
        )},
    )()
    register_provider("complete-adapter", adapter)

    errors = check_payment_settings(None)

    assert "payments.E004" in {error.id for error in errors}
