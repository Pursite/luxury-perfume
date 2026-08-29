"""Validated, server-owned Orders configuration."""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


ORDER_AMOUNT_MAX_DIGITS = 24
ORDER_AMOUNT_DECIMAL_PLACES = 2
_MAX_ORDER_AMOUNT = Decimal("9999999999999999999999.99")
_INVALID_SHIPPING_RATE_MESSAGE = (
    "ORDER_SHIPPING_FLAT_RATE_IRT must be a non-negative decimal amount "
    "with at most 24 digits and 2 decimal places."
)


def get_shipping_flat_rate_irt() -> Decimal:
    """Return a Decimal that fits the persisted Order monetary snapshot field."""
    try:
        amount = Decimal(str(settings.ORDER_SHIPPING_FLAT_RATE_IRT))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ImproperlyConfigured(_INVALID_SHIPPING_RATE_MESSAGE) from exc

    if (
        not amount.is_finite()
        or amount < 0
        or amount.as_tuple().exponent < -ORDER_AMOUNT_DECIMAL_PLACES
        or amount > _MAX_ORDER_AMOUNT
    ):
        raise ImproperlyConfigured(_INVALID_SHIPPING_RATE_MESSAGE)
    return amount
