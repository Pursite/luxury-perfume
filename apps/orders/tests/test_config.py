from decimal import Decimal
import os
import subprocess
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.orders.config import get_shipping_flat_rate_irt


@pytest.mark.parametrize(
    "configured_value",
    ("invalid", "-0.01", "NaN", "Infinity", "350000.001", "10000000000000000000000.00"),
)
def test_shipping_configuration_rejects_values_the_order_money_field_cannot_safely_snapshot(configured_value):
    """Removing amount validation could persist invalid checkout monetary snapshots."""
    with override_settings(ORDER_SHIPPING_FLAT_RATE_IRT=configured_value):
        with pytest.raises(ImproperlyConfigured, match="ORDER_SHIPPING_FLAT_RATE_IRT"):
            get_shipping_flat_rate_irt()


@override_settings(ORDER_SHIPPING_FLAT_RATE_IRT="350000.00")
def test_shipping_configuration_returns_an_exact_two_place_decimal():
    """A float or altered unit would produce an incorrect persisted shipping amount."""
    assert get_shipping_flat_rate_irt() == Decimal("350000.00")


def test_malformed_environment_shipping_value_reaches_the_safe_configuration_error():
    """Eager environment coercion would leak a raw decimal parsing exception at startup."""
    environment = {**os.environ, "ORDER_SHIPPING_FLAT_RATE_IRT": "not-a-decimal"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from apps.orders.config import get_shipping_flat_rate_irt; "
                "from django.core.exceptions import ImproperlyConfigured; "
                "\ntry:\n get_shipping_flat_rate_irt()\n"
                "except ImproperlyConfigured as error:\n print(error)\n"
            ),
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "ORDER_SHIPPING_FLAT_RATE_IRT must be a non-negative decimal amount" in result.stdout
