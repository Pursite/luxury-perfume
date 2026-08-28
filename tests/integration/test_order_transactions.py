"""PostgreSQL-only order locking tests; SQLite cannot validate these races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import (
    CheckoutError,
    CheckoutUserNotFoundError,
    InsufficientStockError,
    create_waiting_order,
)
from apps.orders.services.transitions import (
    TransitionOutcome,
    confirm_verified_payment,
    expire_unpaid_order,
)
from apps.products.services import (
    ProductDeletionProtectedError,
    delete_product_service,
    update_product_from_admin_service,
)
from apps.products.tests.factories import ProductFactory
from apps.users.models import CustomUser
from apps.users.services.user_service import (
    UserDeletionProtectedError,
    delete_users_service,
)
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


def _expire(order):
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )


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
    assert StockReservation.objects.filter(
        status=StockReservation.Status.ACTIVE
    ).count() == 1


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
    assert order.late_payment_detected_at is not None
    assert order.items.get().reservation.status == StockReservation.Status.RELEASED
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
    product.refresh_from_db()
    assert product.stock == 1
    assert StockReservation.objects.filter(
        order_item__order__user=address.user,
        status=StockReservation.Status.ACTIVE,
    ).count() == 1


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
    first_product.refresh_from_db()
    second_product.refresh_from_db()
    assert (first_product.stock, second_product.stock) == (0, 0)
    assert StockReservation.objects.filter(
        status=StockReservation.Status.ACTIVE
    ).count() == 2


def test_e_stale_checkout_reconciliation_racing_expiry_restores_stock_once():
    address = AddressFactory()
    old_product = ProductFactory(stock=5)
    _cart(address=address, product=old_product)
    old_order, _ = _checkout(
        user_id=address.user_id,
        address_id=address.pk,
        key="09ec4390-720e-4b11-b39e-8e5554eae001",
    )
    _expire(old_order)
    new_product = ProductFactory(stock=5)
    CartItem.objects.create(
        cart=Cart.objects.get(user=address.user),
        product=new_product,
        quantity=1,
    )
    barrier = Barrier(2)

    def expire_old():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return expire_unpaid_order(order_id=old_order.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        checkout_future = executor.submit(
            _checkout,
            user_id=address.user_id,
            address_id=address.pk,
            key="2b442dd7-d95d-45cb-a0ac-7581361cd8c2",
            barrier=barrier,
        )
        expiry_future = executor.submit(expire_old)
        replacement, created = checkout_future.result(timeout=20)
        expiry_future.result(timeout=20)

    old_order.refresh_from_db()
    old_product.refresh_from_db()
    new_product.refresh_from_db()
    old_reservation = old_order.items.get().reservation
    assert old_order.status == Order.Status.CANCELLED
    assert old_reservation.status == StockReservation.Status.RELEASED
    assert old_product.stock == 5
    assert replacement.status == Order.Status.WAITING_FOR_PAYMENT
    assert created
    assert new_product.stock == 4


def test_f_stale_reconciliation_racing_verified_payment_obeys_database_deadline():
    valid_address = AddressFactory()
    valid_product = ProductFactory(stock=5)
    _cart(address=valid_address, product=valid_product)
    valid_key = "cf735540-451d-439a-90f8-52f68deca96d"
    valid_order, _ = _checkout(
        user_id=valid_address.user_id,
        address_id=valid_address.pk,
        key=valid_key,
    )
    valid_barrier = Barrier(2)

    def confirm(order_id, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return confirm_verified_payment(order_id=order_id)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        replay_future = executor.submit(
            _checkout,
            user_id=valid_address.user_id,
            address_id=valid_address.pk,
            key=valid_key,
            barrier=valid_barrier,
        )
        confirm_future = executor.submit(confirm, valid_order.pk, valid_barrier)
        replayed_order, replay_created = replay_future.result(timeout=20)
        valid_result = confirm_future.result(timeout=20)

    valid_order.refresh_from_db()
    valid_product.refresh_from_db()
    assert replayed_order.pk == valid_order.pk
    assert not replay_created
    assert valid_result.outcome == TransitionOutcome.APPLIED
    assert valid_order.status == Order.Status.PROCESSING
    assert valid_order.items.get().reservation.status == StockReservation.Status.CONSUMED
    assert valid_product.stock == 4

    expired_address = AddressFactory()
    expired_product = ProductFactory(stock=5)
    _cart(address=expired_address, product=expired_product)
    expired_key = "92f79402-633d-4daa-90c5-bd9102293a62"
    expired_order, _ = _checkout(
        user_id=expired_address.user_id,
        address_id=expired_address.pk,
        key=expired_key,
    )
    _expire(expired_order)
    expired_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        replay_future = executor.submit(
            _checkout,
            user_id=expired_address.user_id,
            address_id=expired_address.pk,
            key=expired_key,
            barrier=expired_barrier,
        )
        confirm_future = executor.submit(confirm, expired_order.pk, expired_barrier)
        replay_future.result(timeout=20)
        late_result = confirm_future.result(timeout=20)

    expired_order.refresh_from_db()
    expired_product.refresh_from_db()
    assert late_result.outcome == TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED
    assert expired_order.status == Order.Status.CANCELLED
    assert expired_order.late_payment_detected_at is not None
    assert expired_order.items.get().reservation.status == StockReservation.Status.RELEASED
    assert expired_product.stock == 5


def test_g_duplicate_same_user_stale_replacement_creates_one_new_order():
    address = AddressFactory()
    old_product = ProductFactory(stock=5)
    _cart(address=address, product=old_product)
    old_key = "65a26d06-747f-4ed8-aaed-326b539447c8"
    old_order, _ = _checkout(
        user_id=address.user_id,
        address_id=address.pk,
        key=old_key,
    )
    _expire(old_order)
    new_product = ProductFactory(stock=5)
    CartItem.objects.create(
        cart=Cart.objects.get(user=address.user),
        product=new_product,
        quantity=1,
    )
    new_key = "36117ca2-ff71-49ba-a443-31a1b9d0af39"
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _checkout,
                user_id=address.user_id,
                address_id=address.pk,
                key=new_key,
                barrier=barrier,
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=20) for future in futures]

    old_order.refresh_from_db()
    old_product.refresh_from_db()
    new_product.refresh_from_db()
    new_order = Order.objects.get(user=address.user, idempotency_key=new_key)
    assert old_order.status == Order.Status.CANCELLED
    assert old_order.items.get().reservation.status == StockReservation.Status.RELEASED
    assert old_product.stock == 5
    assert Order.objects.filter(user=address.user, idempotency_key=new_key).count() == 1
    assert new_order.status == Order.Status.WAITING_FOR_PAYMENT
    assert new_order.items.get().reservation.status == StockReservation.Status.ACTIVE
    assert new_product.stock == 4
    assert {order.pk for order, _created in results} == {new_order.pk}
    assert sorted(created for _order, created in results) == [False, True]
    assert Order.objects.filter(
        user=address.user,
        status=Order.Status.WAITING_FOR_PAYMENT,
    ).count() == 1


def test_h_product_deletion_and_checkout_serialize_without_raw_protected_error():
    deletion_first_address = AddressFactory()
    deletion_first_product = ProductFactory(stock=5)
    _cart(address=deletion_first_address, product=deletion_first_product)
    stale_user = deletion_first_address.user
    deleted = Event()

    def delete_first():
        close_old_connections()
        try:
            deleted_result = delete_product_service(
                product=type(deletion_first_product).objects.get(
                    pk=deletion_first_product.pk
                )
            )
            deleted.set()
            return deleted_result
        finally:
            close_old_connections()

    def checkout_after_delete():
        close_old_connections()
        try:
            assert deleted.wait(timeout=10)
            return create_waiting_order(
                user=stale_user,
                address_id=deletion_first_address.pk,
                idempotency_key="b22a9138-4a35-4ce5-9088-2947a26f330d",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        delete_future = executor.submit(delete_first)
        checkout_future = executor.submit(checkout_after_delete)
        assert delete_future.result(timeout=20)
        with pytest.raises(CheckoutError):
            checkout_future.result(timeout=20)

    assert not type(deletion_first_product).objects.filter(
        pk=deletion_first_product.pk
    ).exists()
    assert not Order.objects.filter(user=stale_user).exists()
    assert not StockReservation.objects.filter(
        order_item__product_id=deletion_first_product.pk
    ).exists()

    checkout_first_address = AddressFactory()
    checkout_first_product = ProductFactory(stock=5)
    _cart(address=checkout_first_address, product=checkout_first_product)
    checkout_reserved = Event()
    allow_checkout_commit = Event()
    delete_started = Event()

    def checkout_first():
        close_old_connections()
        try:
            with transaction.atomic():
                result = create_waiting_order(
                    user=CustomUser.objects.get(pk=checkout_first_address.user_id),
                    address_id=checkout_first_address.pk,
                    idempotency_key="41e75f13-fdb6-4608-81f8-cb7d83b82e04",
                )
                checkout_reserved.set()
                assert allow_checkout_commit.wait(timeout=10)
                return result
        finally:
            close_old_connections()

    def delete_after_checkout_lock():
        close_old_connections()
        try:
            assert checkout_reserved.wait(timeout=10)
            delete_started.set()
            return delete_product_service(
                product=type(checkout_first_product).objects.get(
                    pk=checkout_first_product.pk
                )
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        checkout_future = executor.submit(checkout_first)
        delete_future = executor.submit(delete_after_checkout_lock)
        assert delete_started.wait(timeout=10)
        allow_checkout_commit.set()
        order, created = checkout_future.result(timeout=20)
        with pytest.raises(ProductDeletionProtectedError):
            delete_future.result(timeout=20)

    checkout_first_product.refresh_from_db()
    assert created
    assert Order.objects.filter(pk=order.pk).exists()
    assert order.items.filter(product=checkout_first_product).exists()
    assert order.items.get().reservation.status == StockReservation.Status.ACTIVE
    assert checkout_first_product.stock == 4


def test_i_user_deletion_and_checkout_serialize_to_domain_outcomes():
    deletion_first_address = AddressFactory()
    deletion_first_product = ProductFactory(stock=5)
    _cart(address=deletion_first_address, product=deletion_first_product)
    stale_user = deletion_first_address.user
    deleted = Event()

    def delete_first():
        close_old_connections()
        try:
            result = delete_users_service(
                user_ids=[stale_user.pk],
                allow_privileged=True,
            )
            deleted.set()
            return result
        finally:
            close_old_connections()

    def checkout_after_delete():
        close_old_connections()
        try:
            assert deleted.wait(timeout=10)
            return create_waiting_order(
                user=stale_user,
                address_id=deletion_first_address.pk,
                idempotency_key="4fb94f99-61f8-427e-bdb0-753f83f6b521",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        delete_future = executor.submit(delete_first)
        checkout_future = executor.submit(checkout_after_delete)
        assert delete_future.result(timeout=20) == 1
        with pytest.raises(CheckoutUserNotFoundError):
            checkout_future.result(timeout=20)

    checkout_first_address = AddressFactory()
    checkout_first_product = ProductFactory(stock=5)
    _cart(address=checkout_first_address, product=checkout_first_product)
    checkout_reserved = Event()
    allow_checkout_commit = Event()
    delete_started = Event()

    def checkout_first():
        close_old_connections()
        try:
            with transaction.atomic():
                result = create_waiting_order(
                    user=CustomUser.objects.get(pk=checkout_first_address.user_id),
                    address_id=checkout_first_address.pk,
                    idempotency_key="61badfc4-2865-4393-8608-c9388963fd76",
                )
                checkout_reserved.set()
                assert allow_checkout_commit.wait(timeout=10)
                return result
        finally:
            close_old_connections()

    def delete_after_checkout_lock():
        close_old_connections()
        try:
            assert checkout_reserved.wait(timeout=10)
            delete_started.set()
            return delete_users_service(
                user_ids=[checkout_first_address.user_id],
                allow_privileged=True,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        checkout_future = executor.submit(checkout_first)
        delete_future = executor.submit(delete_after_checkout_lock)
        assert delete_started.wait(timeout=10)
        allow_checkout_commit.set()
        order, created = checkout_future.result(timeout=20)
        with pytest.raises(UserDeletionProtectedError):
            delete_future.result(timeout=20)

    assert created
    assert CustomUser.objects.filter(pk=checkout_first_address.user_id).exists()
    order.refresh_from_db()
    assert order.user_id == checkout_first_address.user_id
    assert order.customer_phone_number == checkout_first_address.user.phone_number
    assert order.items.get().reservation.status == StockReservation.Status.ACTIVE


def test_j_admin_stock_delta_waits_for_checkout_and_preserves_both_mutations():
    address = AddressFactory()
    product = ProductFactory(stock=10)
    _cart(address=address, product=product)
    checkout_reserved = Event()
    allow_checkout_commit = Event()
    admin_started = Event()

    def checkout_with_held_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                result = create_waiting_order(
                    user=CustomUser.objects.get(pk=address.user_id),
                    address_id=address.pk,
                    idempotency_key="023d5d6f-8aaa-402b-91f7-94f88af9f5e1",
                )
                checkout_reserved.set()
                assert allow_checkout_commit.wait(timeout=10)
                return result
        finally:
            close_old_connections()

    def stale_admin_adjustment():
        close_old_connections()
        try:
            assert checkout_reserved.wait(timeout=10)
            admin_started.set()
            return update_product_from_admin_service(
                product_id=product.pk,
                changed_data={},
                original_stock=10,
                submitted_stock=8,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        checkout_future = executor.submit(checkout_with_held_lock)
        admin_future = executor.submit(stale_admin_adjustment)
        assert admin_started.wait(timeout=10)
        allow_checkout_commit.set()
        order, created = checkout_future.result(timeout=20)
        admin_future.result(timeout=20)

    product.refresh_from_db()
    assert created
    assert product.stock == 7
    assert product.stock >= 0
    assert Order.objects.filter(pk=order.pk).exists()
    item = order.items.get()
    assert item.product_id == product.pk
    assert item.reservation.status == StockReservation.Status.ACTIVE
