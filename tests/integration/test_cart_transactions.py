from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event
from time import monotonic

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from apps.cart.models import Cart, CartItem
from apps.cart.services import add_cart_item_service
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.products.tests.factories import ProductFactory
from apps.users.models import CustomUser
from apps.users.tests.factories import UserFactory


pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def _wait_until_postgres_backend_is_blocked_on_lock(*, backend_pid: int) -> None:
    deadline = monotonic() + 10
    with connection.cursor() as cursor:
        while monotonic() < deadline:
            cursor.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                [backend_pid],
            )
            row = cursor.fetchone()
            if row and row[0] == "Lock":
                return
    raise AssertionError(
        f"PostgreSQL backend {backend_pid} did not block on a row lock"
    )


def _thread_add(*, user_id, product_slug, quantity, ready=None):
    close_old_connections()
    try:
        user = CustomUser.objects.get(pk=user_id)
        if ready is not None:
            ready.wait(timeout=10)
        item, created = add_cart_item_service(
            user=user,
            product_slug=product_slug,
            quantity=quantity,
        )
        return item.quantity, created
    finally:
        close_old_connections()


def test_concurrent_first_mutations_create_one_cart_and_keep_both_items():
    user = UserFactory()
    first_product = ProductFactory(stock=10)
    second_product = ProductFactory(stock=10)
    ready = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _thread_add,
                user_id=user.pk,
                product_slug=product.slug,
                quantity=1,
                ready=ready,
            )
            for product in (first_product, second_product)
        ]
        results = [future.result(timeout=20) for future in futures]

    cart = Cart.objects.get(user=user)
    assert results == [(1, True), (1, True)]
    assert Cart.objects.filter(user=user).count() == 1
    assert set(cart.items.values_list("product_id", flat=True)) == {
        first_product.pk,
        second_product.pk,
    }


def test_concurrent_same_item_posts_preserve_both_increments():
    item = CartItemFactory(quantity=1, product__stock=100)
    ready = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _thread_add,
                user_id=item.cart.user_id,
                product_slug=item.product.slug,
                quantity=quantity,
                ready=ready,
            )
            for quantity in (2, 3)
        ]
        results = [future.result(timeout=20) for future in futures]

    item.refresh_from_db()
    observed_quantities = sorted(quantity for quantity, _ in results)
    assert observed_quantities[-1] == 6
    assert observed_quantities[0] in (3, 4)
    assert all(created is False for _, created in results)
    assert item.quantity == 6


def test_postgresql_cart_constraints_remain_authoritative():
    cart = CartFactory()
    product = ProductFactory()
    CartItemFactory(cart=cart, product=product)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CartFactory(user=cart.user)

    with pytest.raises(IntegrityError) as unique_error:
        with transaction.atomic():
            CartItemFactory(cart=cart, product=product)
    assert (
        unique_error.value.__cause__.diag.constraint_name
        == "cart_unique_product_per_cart"
    )

    with pytest.raises(IntegrityError) as quantity_error:
        with transaction.atomic():
            CartItem.objects.create(
                cart=cart,
                product=ProductFactory(),
                quantity=0,
            )
    assert (
        quantity_error.value.__cause__.diag.constraint_name
        == "cart_item_quantity_gte_1"
    )


def test_blocked_user_mutation_does_not_serialize_another_user():
    first_user = UserFactory()
    second_user = UserFactory()
    product = ProductFactory(stock=100)
    first_user_locked = Event()
    release_first_user = Event()
    blocked_backend_pid = Queue()

    def hold_first_user_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                CustomUser.objects.select_for_update().get(pk=first_user.pk)
                first_user_locked.set()
                if not release_first_user.wait(timeout=20):
                    raise TimeoutError("first user lock was not released")
        finally:
            close_old_connections()

    def add_for_blocked_user():
        close_old_connections()
        try:
            connection.ensure_connection()
            blocked_backend_pid.put(connection.connection.info.backend_pid)
            user = CustomUser.objects.get(pk=first_user.pk)
            return add_cart_item_service(
                user=user,
                product_slug=product.slug,
                quantity=1,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as executor:
        blocker = executor.submit(hold_first_user_lock)
        assert first_user_locked.wait(timeout=10)
        blocked_mutation = executor.submit(add_for_blocked_user)
        backend_pid = blocked_backend_pid.get(timeout=10)
        _wait_until_postgres_backend_is_blocked_on_lock(backend_pid=backend_pid)

        unrelated_mutation = executor.submit(
            _thread_add,
            user_id=second_user.pk,
            product_slug=product.slug,
            quantity=1,
        )
        try:
            unrelated_result = unrelated_mutation.result(timeout=10)
        finally:
            release_first_user.set()

        blocker.result(timeout=20)
        blocked_mutation.result(timeout=20)

    assert unrelated_result == (1, True)
    assert CartItem.objects.filter(cart__user=first_user, product=product).exists()
    assert CartItem.objects.filter(cart__user=second_user, product=product).exists()
