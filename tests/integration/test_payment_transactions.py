"""PostgreSQL-only Payment lock and idempotency races."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Event, Lock, get_ident

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order
from apps.orders.services.transitions import expire_unpaid_order
from apps.payments.models import Payment, Refund
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    PaymentVerificationResult,
    RefundOutcome,
    RefundResult,
    VerificationOutcome,
)
from apps.payments.providers.registry import register_provider
from apps.payments.services import initialization
from apps.payments.services.refunds import execute_refund
from apps.payments.services.verification import verify_payment
from apps.payments.tests.factories import RefundFactory
from apps.products.tests.factories import ProductFactory
from apps.users.models import CustomUser
from apps.users.tests.factories import AddressFactory


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


class ConcurrentProvider:
    def __init__(self):
        self.calls = 0
        self.lock = Lock()

    def create_payment(self, **kwargs):
        with self.lock:
            self.calls += 1
        return PaymentInitiationResult(
            outcome=InitiationOutcome.READY,
            provider_session_id=f"session-{kwargs['payment_uuid']}",
            redirect_url=f"https://gateway.example.test/pay/{kwargs['payment_uuid']}",
        )

    def build_redirect_url(self, provider_session_id):
        return f"https://gateway.example.test/pay/{provider_session_id.removeprefix('session-')}"


class BlockingVerificationProvider(ConcurrentProvider):
    def __init__(self):
        super().__init__()
        self.verify_calls = 0
        self.verification_entered = Event()
        self.release_verification = Event()

    def verify_payment(self, **kwargs):
        with self.lock:
            self.verify_calls += 1
        self.verification_entered.set()
        assert self.release_verification.wait(timeout=10)
        return PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="transaction-blocking",
            captured_amount=kwargs["expected_amount"],
            captured_currency=kwargs["expected_currency"],
        )

    def refund_payment(self, **kwargs):
        return RefundResult(outcome=RefundOutcome.AMBIGUOUS, diagnostic_code="still_pending")


class BlockingRefundProvider:
    def __init__(self):
        self.refund_calls = 0
        self.lock = Lock()
        self.refund_entered = Event()
        self.release_refund = Event()

    def refund_payment(self, **kwargs):
        with self.lock:
            self.refund_calls += 1
        self.refund_entered.set()
        assert self.release_refund.wait(timeout=10)
        return RefundResult(
            outcome=RefundOutcome.REFUNDED,
            provider_refund_id="refund-blocking",
        )


def _checkout_and_initialize(settings, provider, *, provider_name, key):
    register_provider(provider_name, provider)
    settings.PAYMENT_PROVIDER = provider_name
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    address = AddressFactory()
    cart = Cart.objects.create(user=address.user)
    product = ProductFactory(stock=2, price=Decimal("100.00"), discount_price=None)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    initialized = initialization.initialize_payment(
        user=address.user,
        idempotency_key=key,
        address_uuid=address.pk,
        initiator_ip="198.51.100.8",
        initiator_user_agent="browser",
        request_id="a" * 32,
    )
    return initialized, product


def test_concurrent_identical_initialization_replays_one_durable_payment(settings, monkeypatch):
    provider = ConcurrentProvider()
    register_provider("concurrent", provider)
    settings.PAYMENT_PROVIDER = "concurrent"
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    address = AddressFactory()
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(
        cart=cart,
        product=ProductFactory(stock=2, price=Decimal("100.00"), discount_price=None),
        quantity=1,
    )
    lookup_barrier = Barrier(2)
    lookup_lock = Lock()
    lookup_counts = {}
    real_lookup = initialization._find_existing_payment

    def synchronized_initial_lookup(idempotency_key):
        thread_id = get_ident()
        with lookup_lock:
            lookup_counts[thread_id] = lookup_counts.get(thread_id, 0) + 1
            first_lookup = lookup_counts[thread_id] == 1
        if first_lookup:
            lookup_barrier.wait(timeout=10)
        return real_lookup(idempotency_key)

    monkeypatch.setattr(initialization, "_find_existing_payment", synchronized_initial_lookup)
    key = "17242d22-f4da-428c-b263-176682a4d2fd"

    def initialize():
        close_old_connections()
        try:
            return initialization.initialize_payment(
                user=CustomUser.objects.get(pk=address.user_id),
                idempotency_key=key,
                address_uuid=address.pk,
                initiator_ip="198.51.100.8",
                initiator_user_agent="browser",
                request_id="a" * 32,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result(timeout=20) for future in (executor.submit(initialize), executor.submit(initialize))]

    assert results[0].payment.pk == results[1].payment.pk
    assert sorted(result.created for result in results) == [False, True]
    assert provider.calls == 1
    assert Payment.objects.filter(idempotency_key=key).count() == 1


def test_concurrent_verification_claim_permits_one_provider_call(settings):
    provider = BlockingVerificationProvider()
    initialized, _product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="verify-race",
        key="837b74e4-96df-47cd-804e-06c3c65db1f4",
    )

    def verify():
        close_old_connections()
        try:
            return verify_payment(
                provider="verify-race",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(verify)
        assert provider.verification_entered.wait(timeout=10)
        contender = executor.submit(verify)
        contender_result = contender.result(timeout=10)
        provider.release_verification.set()
        winner_result = winner.result(timeout=20)

    initialized.payment.refresh_from_db()
    initialized.order.refresh_from_db()
    assert contender_result.pending is True
    assert winner_result.payment.status == Payment.Status.VERIFIED
    assert initialized.payment.applied_to_order_at is not None
    assert initialized.order.status == Order.Status.PROCESSING
    assert provider.verify_calls == 1


def test_verification_delayed_by_expiry_becomes_late_refund(settings):
    provider = BlockingVerificationProvider()
    initialized, product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="expiry-race",
        key="76eb7320-0998-4701-bd95-40961d7d7294",
    )
    now = timezone.now()
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=now - timedelta(minutes=20),
        reservation_expires_at=now - timedelta(seconds=1),
    )

    def verify():
        close_old_connections()
        try:
            return verify_payment(
                provider="expiry-race",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(verify)
        assert provider.verification_entered.wait(timeout=10)
        expired = expire_unpaid_order(order_id=initialized.order.pk)
        provider.release_verification.set()
        result = future.result(timeout=20)

    initialized.order.refresh_from_db()
    product.refresh_from_db()
    assert expired.changed is True
    assert result.payment.status == Payment.Status.VERIFIED
    assert initialized.order.status == Order.Status.CANCELLED
    assert initialized.order.late_payment_detected_at is not None
    assert product.stock == 2
    assert Refund.objects.filter(
        payment=initialized.payment,
        reason=Refund.Reason.LATE_PAYMENT,
    ).count() == 1


def test_concurrent_refund_execution_permits_one_provider_call():
    provider = BlockingRefundProvider()
    register_provider("refund-race", provider)
    refund = RefundFactory(
        provider="refund-race",
        payment__provider="refund-race",
    )

    def execute():
        close_old_connections()
        try:
            return execute_refund(refund_id=refund.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(execute)
        assert provider.refund_entered.wait(timeout=10)
        contender = executor.submit(execute)
        contender_result = contender.result(timeout=10)
        provider.release_refund.set()
        winner_result = winner.result(timeout=20)

    refund.refresh_from_db()
    assert contender_result.status == Refund.Status.PROCESSING
    assert winner_result.status == Refund.Status.REFUNDED
    assert refund.status == Refund.Status.REFUNDED
    assert refund.provider_refund_id == "refund-blocking"
    assert provider.refund_calls == 1
