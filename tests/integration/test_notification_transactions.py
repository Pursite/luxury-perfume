"""PostgreSQL races for durable Order SMS notifications."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event, Lock

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.lib.sms.base import SmsSendOutcome, SmsSendResult
from apps.lib.sms.registry import register_provider
from apps.notifications.models import SmsDelivery
from apps.notifications.services import events
from apps.notifications.services.delivery import execute_delivery
from apps.notifications.tasks import sweep_due_sms_deliveries
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import InvalidOrderTransitionError, confirm_verified_payment, mark_order_shipped
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


class BlockingSmsProvider:
    supports_idempotent_send = True

    def __init__(self):
        self.calls = 0
        self.lock = Lock()
        self.entered = Event()
        self.release = Event()

    def configuration_errors(self):
        return ()

    def send_sms(self, **kwargs):
        with self.lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=10)
        return SmsSendResult(
            outcome=SmsSendOutcome.ACCEPTED,
            provider_message_id="notification-worker-message",
        )


def _order_with_reservation():
    address = AddressFactory(user__phone_number="09129876543")
    product = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    order, _ = create_waiting_order(
        user=address.user,
        address_id=address.pk,
        idempotency_key="52e882cb-5bb5-4c02-9acc-3dd7873f3540",
    )
    return order, product


def _confirm_in_thread(*, order_id, barrier):
    close_old_connections()
    try:
        barrier.wait(timeout=10)
        return confirm_verified_payment(order_id=order_id)
    finally:
        close_old_connections()


def _execute_delivery_in_thread(*, delivery_id):
    close_old_connections()
    try:
        return execute_delivery(delivery_id=delivery_id)
    finally:
        close_old_connections()


def test_concurrent_payment_confirmation_creates_one_delivery_per_eligible_superuser(settings, monkeypatch):
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "test-sms"
    monkeypatch.setattr(events, "_enqueue_after_commit", lambda delivery: None)
    owners = [
        UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True),
        UserFactory(phone_number="09122222222", is_staff=True, is_superuser=True),
    ]
    order, product = _order_with_reservation()
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result(timeout=20)
            for future in (
                executor.submit(_confirm_in_thread, order_id=order.pk, barrier=barrier),
                executor.submit(_confirm_in_thread, order_id=order.pk, barrier=barrier),
            )
        ]

    order.refresh_from_db()
    product.refresh_from_db()
    assert sum(outcome.changed for outcome in outcomes) == 1
    assert order.status == Order.Status.PROCESSING
    assert product.stock == 1
    assert order.items.get().reservation.status == StockReservation.Status.CONSUMED
    assert SmsDelivery.objects.filter(
        order=order,
        event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
    ).count() == 1
    assert set(
        SmsDelivery.objects.filter(
            order=order,
            event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
        ).values_list("recipient_user_id", flat=True)
    ) == {owner.pk for owner in owners}


def test_concurrent_shipping_creates_exactly_one_customer_delivery(settings, monkeypatch):
    settings.SMS_ENABLED = True
    monkeypatch.setattr(events, "_enqueue_after_commit", lambda delivery: None)
    order, _product = _order_with_reservation()
    confirm_verified_payment(order_id=order.pk)
    barrier = Barrier(2)

    def ship():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return mark_order_shipped(order_id=order.pk)
            except InvalidOrderTransitionError:
                return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(ship) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    order.refresh_from_db()
    assert sum(result is not None for result in results) == 1
    assert order.status == Order.Status.SHIPPED
    assert SmsDelivery.objects.filter(
        order=order,
        event_type=SmsDelivery.EventType.CUSTOMER_ORDER_SHIPPED,
    ).count() == 1


def test_concurrent_delivery_workers_make_one_provider_call(settings):
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "blocking-sms"
    provider = BlockingSmsProvider()
    register_provider("blocking-sms", provider)
    order, _product = _order_with_reservation()
    delivery = SmsDelivery.objects.create(
        order=order,
        event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
        recipient_type=SmsDelivery.RecipientType.CUSTOMER,
        recipient_phone=order.customer_phone_number,
        provider="blocking-sms",
        status=SmsDelivery.Status.PENDING,
        next_retry_at=timezone.now(),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_execute_delivery_in_thread, delivery_id=delivery.pk)
        assert provider.entered.wait(timeout=10)
        second = executor.submit(_execute_delivery_in_thread, delivery_id=delivery.pk)
        assert second.result(timeout=20) is None
        provider.release.set()
        first.result(timeout=20)

    delivery.refresh_from_db()
    assert provider.calls == 1
    assert delivery.status == SmsDelivery.Status.SENT


def test_sweeper_and_direct_delivery_execution_converge_safely(settings, monkeypatch):
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "sweeper-sms"
    provider = BlockingSmsProvider()
    register_provider("sweeper-sms", provider)
    order, _product = _order_with_reservation()
    delivery = SmsDelivery.objects.create(
        order=order,
        event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
        recipient_type=SmsDelivery.RecipientType.CUSTOMER,
        recipient_phone=order.customer_phone_number,
        provider="sweeper-sms",
        status=SmsDelivery.Status.PENDING,
        next_retry_at=timezone.now(),
    )
    monkeypatch.setattr(
        "apps.notifications.tasks.execute_sms_delivery_task.apply_async",
        lambda *, args, **kwargs: execute_delivery(delivery_id=args[0]),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        direct = executor.submit(_execute_delivery_in_thread, delivery_id=delivery.pk)
        assert provider.entered.wait(timeout=10)
        sweep = executor.submit(sweep_due_sms_deliveries.run)
        assert sweep.result(timeout=20) == 0
        provider.release.set()
        direct.result(timeout=20)

    delivery.refresh_from_db()
    assert provider.calls == 1
    assert delivery.status == SmsDelivery.Status.SENT
