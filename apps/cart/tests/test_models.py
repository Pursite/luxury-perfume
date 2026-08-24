from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.cart.models import Cart, CartItem
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.products.models import Product
from apps.products.tests.factories import ProductFactory
from apps.users.models import CustomUser
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def test_database_allows_only_one_cart_per_user():
    user = UserFactory()
    CartFactory(user=user)

    with pytest.raises(IntegrityError), transaction.atomic():
        CartFactory(user=user)


def test_database_allows_only_one_item_per_cart_and_product():
    cart = CartFactory()
    product = ProductFactory()
    CartItemFactory(cart=cart, product=product)

    with pytest.raises(IntegrityError), transaction.atomic():
        CartItemFactory(cart=cart, product=product)


def test_database_rejects_quantity_below_one():
    item = CartItem(
        cart=CartFactory(),
        product=ProductFactory(),
        quantity=0,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        item.save(force_insert=True)


def test_user_deletion_cascades_to_cart_and_items():
    item = CartItemFactory()
    user_id = item.cart.user_id

    CustomUser.objects.get(pk=user_id).delete()

    assert Cart.objects.filter(user_id=user_id).exists() is False
    assert CartItem.objects.filter(pk=item.pk).exists() is False


def test_product_deletion_removes_item_but_retains_cart():
    item = CartItemFactory()
    cart_id = item.cart_id

    Product.objects.get(pk=item.product_id).delete()

    assert Cart.objects.filter(pk=cart_id).exists() is True
    assert CartItem.objects.filter(pk=item.pk).exists() is False


def test_cart_item_derives_live_price_stock_and_availability():
    item = CartItemFactory(
        quantity=2,
        product__price=Decimal("100.00"),
        product__discount_price=Decimal("80.00"),
        product__stock=2,
        product__is_active=True,
    )

    assert item.unit_price == Decimal("80.00")
    assert item.line_total == Decimal("160.00")
    assert item.available_stock == 2
    assert item.available is True

    item.product.stock = 1
    item.product.is_active = False

    assert item.available_stock == 1
    assert item.available is False


def test_cart_models_persist_no_price_stock_or_status_snapshots():
    cart_fields = {field.name for field in Cart._meta.get_fields()}
    item_fields = {field.name for field in CartItem._meta.get_fields()}

    forbidden_fields = {
        "price",
        "unit_price",
        "line_total",
        "total",
        "total_price",
        "stock",
        "stock_snapshot",
        "price_snapshot",
        "availability",
        "available",
        "status",
        "expiration",
    }

    assert forbidden_fields.isdisjoint(cart_fields)
    assert forbidden_fields.isdisjoint(item_fields)
