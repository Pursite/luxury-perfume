import pytest

from apps.cart.serializers import (
    CartItemAddInputSerializer,
    CartItemQuantityInputSerializer,
)


@pytest.mark.parametrize("quantity", [0, -1])
def test_cart_input_serializers_reject_nonpositive_quantity(quantity):
    add_serializer = CartItemAddInputSerializer(
        data={"product_slug": "product", "quantity": quantity}
    )
    update_serializer = CartItemQuantityInputSerializer(data={"quantity": quantity})

    assert add_serializer.is_valid() is False
    assert update_serializer.is_valid() is False
    assert "quantity" in add_serializer.errors
    assert "quantity" in update_serializer.errors


def test_add_input_requires_product_slug_and_quantity():
    serializer = CartItemAddInputSerializer(data={})

    assert serializer.is_valid() is False
    assert set(serializer.errors) == {"product_slug", "quantity"}


def test_update_input_requires_quantity_even_for_patch():
    serializer = CartItemQuantityInputSerializer(data={})

    assert serializer.is_valid() is False
    assert set(serializer.errors) == {"quantity"}
