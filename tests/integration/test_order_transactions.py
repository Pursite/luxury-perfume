"""PostgreSQL-only order locking tests; SQLite cannot validate these races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order
from apps.orders.services.checkout import InsufficientStockError, create_waiting_order
from apps.orders.services.transitions import confirm_verified_payment, expire_unpaid_order
from apps.products.tests.factories import ProductFactory
from apps.users.models import CustomUser
from apps.users.tests.factories import AddressFactory


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def _checkout(*, user_id, address_id, key, barrier=None):
    close_old_connections()
    try:
        if barrier is not None:
            barrier.wait(timeout=10)
        return create_waiting_order(
            user=CustomUser.objects.get(pk=user_id), address_id=address_id, idempotency_key=key
        )
    finally:
        close_old_connections()


def _cart(*, address, product, quantity=1):
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)


def test_a_two_buyers_racing_for_last_item_create_exactly_one_reservation():
    product = ProductFactory(stock=1)
    first, second = AddressFactory(), AddressFactory()
    _cart(address=first, product=product)
    _cart(address=second, product=product)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_checkout, user_id=address.user_id, address_id=address.pk, key=key, barrier=barrier)
            for address, key in ((first, "51fd5dd0-5e5a-4b03-b3ea-8900bdb8c466"), (second, "e5579fbb-2cbd-4e3f-b305-c6baf81e656d"))
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=20))
            except InsufficientStockError:
                outcomes.append(None)
    product.refresh_from_db()
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert product.stock == 0
    assert Order.objects.filter(status=Order.Status.WAITING_FOR_PAYMENT).count() == 1


def test_b_payment_confirmation_racing_expiry_has_one_consistent_winner():
    address = AddressFactory()
    product = ProductFactory(stock=1)
    _cart(address=address, product=product)
    order, _ = _checkout(user_id=address.user_id, address_id=address.pk, key="de11cf0a-297c-4c31-9c5a-e09f22ba8877")
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )
    barrier = Barrier(2)

    def transition(fn):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return fn(order_id=order.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(transition, expire_unpaid_order)
        second = executor.submit(transition, confirm_verified_payment)
        first.result(timeout=20)
        second.result(timeout=20)
    product.refresh_from_db()
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert product.stock == 1


def test_c_duplicate_same_user_checkout_key_creates_one_logical_order():
    address = AddressFactory()
    product = ProductFactory(stock=2)
    _cart(address=address, product=product)
    key = "770b9ec0-1e7a-42dc-8eec-2f6d1a3a7fed"
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(_checkout, user_id=address.user_id, address_id=address.pk, key=key, barrier=barrier),
                executor.submit(_checkout, user_id=address.user_id, address_id=address.pk, key=key, barrier=barrier),
            ]
        ]
    assert results[0][0].pk == results[1][0].pk
    assert sorted(created for _order, created in results) == [False, True]
    assert Order.objects.filter(user=address.user, idempotency_key=key).count() == 1


def test_d_multi_product_checkouts_lock_by_product_pk_without_deadlock():
    first_product, second_product = ProductFactory(stock=1), ProductFactory(stock=1)
    first, second = AddressFactory(), AddressFactory()
    _cart(address=first, product=first_product)
    CartItem.objects.create(cart=Cart.objects.get(user=first.user), product=second_product, quantity=1)
    _cart(address=second, product=second_product)
    CartItem.objects.create(cart=Cart.objects.get(user=second.user), product=first_product, quantity=1)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_checkout, user_id=address.user_id, address_id=address.pk, key=key, barrier=barrier)
            for address, key in ((first, "12d59c18-74e9-4467-95b2-929c68d0b31b"), (second, "71bb99c2-1251-4340-a07f-61e11673888e"))
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=20))
            except InsufficientStockError:
                results.append(None)
    assert sum(result is not None for result in results) == 1
