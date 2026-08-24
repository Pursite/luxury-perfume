import pytest

from apps.cart.selectors import get_cart_items_for_user
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.products.models import ProductImage
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def test_selector_returns_only_owned_items_in_stable_order():
    cart = CartFactory()
    first = CartItemFactory(cart=cart)
    second = CartItemFactory(cart=cart)
    CartItemFactory()

    items = get_cart_items_for_user(user=cart.user)

    assert [item.pk for item in items] == [first.pk, second.pk]


def test_selector_keeps_inactive_and_zero_stock_products():
    cart = CartFactory()
    inactive = CartItemFactory(cart=cart, product__is_active=False)
    zero_stock = CartItemFactory(cart=cart, product__stock=0)

    items = get_cart_items_for_user(user=cart.user)

    assert [item.pk for item in items] == [inactive.pk, zero_stock.pk]
    assert [item.available for item in items] == [False, False]


def test_selector_eager_loads_products_and_images_in_two_queries(
    django_assert_num_queries,
):
    cart = CartFactory()
    products = [ProductFactory() for _ in range(3)]
    for index, product in enumerate(products):
        CartItemFactory(cart=cart, product=product)
        ProductImage.objects.create(
            product=product,
            image=f"products/cart-{index}.jpg",
            display_order=index,
        )

    with django_assert_num_queries(2):
        items = get_cart_items_for_user(user=cart.user)
        loaded = [
            (
                item.product.name,
                [image.image.name for image in item.product._cart_images],
            )
            for item in items
        ]

    assert len(loaded) == 3


def test_selector_returns_empty_list_without_creating_cart():
    user = UserFactory()

    assert get_cart_items_for_user(user=user) == []
