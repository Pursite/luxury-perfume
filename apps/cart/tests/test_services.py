import pytest

from apps.cart.models import Cart, CartItem
from apps.cart.services import (
    CartItemNotFoundError,
    CartProductUnavailableError,
    CartStockExceededError,
    add_cart_item_service,
    clear_cart_service,
    remove_cart_item_service,
    update_cart_item_quantity_service,
)
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def test_add_lazily_creates_cart_and_item():
    user = UserFactory()
    product = ProductFactory(stock=5)

    item, created = add_cart_item_service(
        user=user,
        product_slug=product.slug,
        quantity=2,
    )

    assert created is True
    assert item.cart.user == user
    assert item.product == product
    assert item.quantity == 2
    assert Cart.objects.filter(user=user).count() == 1


def test_repeated_add_increments_existing_quantity():
    item = CartItemFactory(quantity=2, product__stock=10)

    updated, created = add_cart_item_service(
        user=item.cart.user,
        product_slug=item.product.slug,
        quantity=3,
    )

    assert created is False
    assert updated.pk == item.pk
    assert updated.quantity == 5
    assert CartItem.objects.get(pk=item.pk).quantity == 5


@pytest.mark.parametrize("is_active", [False])
def test_add_rejects_inactive_product_without_creating_cart(is_active):
    user = UserFactory()
    product = ProductFactory(is_active=is_active, stock=5)

    with pytest.raises(CartProductUnavailableError):
        add_cart_item_service(
            user=user,
            product_slug=product.slug,
            quantity=1,
        )

    assert Cart.objects.filter(user=user).exists() is False


def test_add_rejects_missing_product_without_creating_cart():
    user = UserFactory()

    with pytest.raises(CartProductUnavailableError):
        add_cart_item_service(
            user=user,
            product_slug="missing-product",
            quantity=1,
        )

    assert Cart.objects.filter(user=user).exists() is False


@pytest.mark.parametrize(
    ("existing_quantity", "submitted_quantity", "stock"),
    [(0, 3, 2), (2, 2, 3)],
)
def test_add_rejects_result_above_current_stock(
    existing_quantity,
    submitted_quantity,
    stock,
):
    user = UserFactory()
    product = ProductFactory(stock=stock)
    if existing_quantity:
        CartItemFactory(
            cart__user=user,
            product=product,
            quantity=existing_quantity,
        )

    with pytest.raises(CartStockExceededError):
        add_cart_item_service(
            user=user,
            product_slug=product.slug,
            quantity=submitted_quantity,
        )

    if existing_quantity:
        assert CartItem.objects.get(cart__user=user, product=product).quantity == 2
    else:
        assert Cart.objects.filter(user=user).exists() is False


def test_update_sets_absolute_quantity_for_owned_item():
    item = CartItemFactory(quantity=2, product__stock=10)

    updated = update_cart_item_quantity_service(
        user=item.cart.user,
        product_slug=item.product.slug,
        quantity=4,
    )

    assert updated.quantity == 4
    assert CartItem.objects.get(pk=item.pk).quantity == 4


def test_update_allows_retained_inactive_item_with_sufficient_stock():
    item = CartItemFactory(
        quantity=2,
        product__is_active=False,
        product__stock=5,
    )

    updated = update_cart_item_quantity_service(
        user=item.cart.user,
        product_slug=item.product.slug,
        quantity=3,
    )

    assert updated.quantity == 3
    assert updated.available is False


def test_update_rejects_quantity_above_current_stock_without_partial_write():
    item = CartItemFactory(quantity=2, product__stock=3)

    with pytest.raises(CartStockExceededError):
        update_cart_item_quantity_service(
            user=item.cart.user,
            product_slug=item.product.slug,
            quantity=4,
        )

    assert CartItem.objects.get(pk=item.pk).quantity == 2


def test_update_cannot_access_another_users_item():
    item = CartItemFactory(product__stock=5)
    other_user = UserFactory()

    with pytest.raises(CartItemNotFoundError):
        update_cart_item_quantity_service(
            user=other_user,
            product_slug=item.product.slug,
            quantity=2,
        )


def test_remove_deletes_only_the_owned_item():
    product = ProductFactory(stock=5)
    owned_item = CartItemFactory(product=product)
    other_item = CartItemFactory(product=product)

    remove_cart_item_service(
        user=owned_item.cart.user,
        product_slug=product.slug,
    )

    assert CartItem.objects.filter(pk=owned_item.pk).exists() is False
    assert CartItem.objects.filter(pk=other_item.pk).exists() is True


def test_remove_missing_owned_item_raises_not_found():
    item = CartItemFactory()

    with pytest.raises(CartItemNotFoundError):
        remove_cart_item_service(
            user=UserFactory(),
            product_slug=item.product.slug,
        )


def test_clear_retains_existing_cart_and_removes_all_items():
    cart = CartFactory()
    CartItemFactory(cart=cart)
    CartItemFactory(cart=cart)

    clear_cart_service(user=cart.user)

    assert Cart.objects.filter(pk=cart.pk).exists() is True
    assert CartItem.objects.filter(cart=cart).exists() is False


def test_clear_does_not_create_missing_cart():
    user = UserFactory()

    clear_cart_service(user=user)

    assert Cart.objects.filter(user=user).exists() is False
