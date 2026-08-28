"""PostgreSQL-only Payment lock and idempotency races."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Event, Lock, get_ident

import pytest
from django.db import close_old_connections
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order
from apps.orders.services.checkout import ActiveCheckoutError
from apps.orders.services.transitions import cancel_failed_payment, expire_unpaid_order
from apps.payments.exceptions import (
    PaymentAttemptInProgressError,
    ProviderProtocolError,
    ProviderSecurityError,
    RefundNotEligibleError,
)
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
from apps.payments.services.reconciliation import reconcile_payment
from apps.payments.services.refunds import execute_refund, record_manual_refund_completion
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


class SessionVerificationProvider(ConcurrentProvider):
    """A deterministic fake whose verification identity is keyed by session."""

    def __init__(self, *, amount_overrides=None, transaction_overrides=None):
        super().__init__()
        self.verify_calls = 0
        self.amount_overrides = amount_overrides or {}
        self.transaction_overrides = transaction_overrides or {}

    def verify_payment(self, **kwargs):
        with self.lock:
            self.verify_calls += 1
        session = kwargs["provider_session_id"]
        return PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id=self.transaction_overrides.get(session, f"transaction-{session}"),
            captured_amount=self.amount_overrides.get(session, kwargs["expected_amount"]),
            captured_currency=kwargs["expected_currency"],
        )

    def refund_payment(self, **kwargs):
        return RefundResult(
            outcome=RefundOutcome.REFUNDED,
            provider_refund_id=f"refund-{kwargs['refund_uuid']}",
        )


class BlockingInitializationProvider(ConcurrentProvider):
    def __init__(self):
        super().__init__()
        self.initiation_entered = Event()
        self.release_initiation = Event()

    def create_payment(self, **kwargs):
        with self.lock:
            self.calls += 1
        self.initiation_entered.set()
        assert self.release_initiation.wait(timeout=10)
        return PaymentInitiationResult(
            outcome=InitiationOutcome.READY,
            provider_session_id=f"session-{kwargs['payment_uuid']}",
            redirect_url=f"https://gateway.example.test/pay/{kwargs['payment_uuid']}",
        )


class BarrierVerificationProvider(SessionVerificationProvider):
    def __init__(self, *, parties, transaction_id):
        super().__init__()
        self.verify_barrier = Barrier(parties)
        self.transaction_id = transaction_id

    def verify_payment(self, **kwargs):
        with self.lock:
            self.verify_calls += 1
        self.verify_barrier.wait(timeout=10)
        return PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id=self.transaction_id,
            captured_amount=kwargs["expected_amount"],
            captured_currency=kwargs["expected_currency"],
        )


class CallbackOutcomeProvider(SessionVerificationProvider):
    def __init__(self):
        super().__init__()
        self.outcomes = {}

    def verify_payment(self, **kwargs):
        with self.lock:
            self.verify_calls += 1
        outcome = self.outcomes[kwargs["provider_session_id"]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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


def _old_failed_attempt_with_current_open_attempt(settings, provider, *, provider_name, key, retry_key):
    old, product = _checkout_and_initialize(
        settings,
        provider,
        provider_name=provider_name,
        key=key,
    )
    Payment.objects.filter(pk=old.payment.pk).update(
        status=Payment.Status.FAILED,
        failed_at=timezone.now(),
        failure_code="initiation_rejected",
        operation_token=None,
        operation_started_at=None,
    )
    current = initialization.initialize_payment(
        user=old.order.user,
        idempotency_key=retry_key,
        order_uuid=old.order.uuid,
        initiator_ip="198.51.100.8",
        initiator_user_agent="browser",
        request_id="h" * 32,
    )
    return old, current, product


def _verify_in_separate_connection(*, provider_name, provider_session_id):
    def verify():
        close_old_connections()
        try:
            return verify_payment(
                provider=provider_name,
                provider_session_id=provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(verify).result(timeout=20)


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


def test_race_b_initialize_with_different_keys_creates_one_open_attempt(settings, monkeypatch):
    provider = ConcurrentProvider()
    register_provider("initialize-different", provider)
    settings.PAYMENT_PROVIDER = "initialize-different"
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
    barrier = Barrier(2)
    real_lookup = initialization._find_existing_payment

    def synchronize_first_lookup(key):
        barrier.wait(timeout=10)
        return real_lookup(key)

    monkeypatch.setattr(initialization, "_find_existing_payment", synchronize_first_lookup)

    def initialize(key):
        close_old_connections()
        try:
            return initialization.initialize_payment(
                user=CustomUser.objects.get(pk=address.user_id),
                idempotency_key=key,
                address_uuid=address.pk,
                initiator_ip="198.51.100.8",
                initiator_user_agent="browser",
                request_id="b" * 32,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(initialize, "03498340-6f23-4e3e-a442-8a68b3ef5682"),
            executor.submit(initialize, "92d3b1fe-2d4e-478b-9f6f-f2869a126103"),
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("success", future.result(timeout=20)))
            except (ActiveCheckoutError, PaymentAttemptInProgressError) as exc:
                outcomes.append(("blocked", exc))

    assert [kind for kind, _value in outcomes].count("success") == 1
    assert [kind for kind, _value in outcomes].count("blocked") == 1
    assert Payment.objects.filter(order__user=address.user).count() == 1
    payment = Payment.objects.get(order__user=address.user)
    assert payment.status in Payment.OPEN_STATUSES
    assert provider.calls == 1


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


def test_race_e_expiry_during_initiation_persistence_never_returns_redirect(settings):
    provider = BlockingInitializationProvider()
    register_provider("init-expiry", provider)
    settings.PAYMENT_PROVIDER = "init-expiry"
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    address = AddressFactory()
    cart = Cart.objects.create(user=address.user)
    product = ProductFactory(stock=2, price=Decimal("100.00"), discount_price=None)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    def initialize():
        close_old_connections()
        try:
            return initialization.initialize_payment(
                user=CustomUser.objects.get(pk=address.user_id),
                idempotency_key="17817c04-245c-4e7e-a049-7fa7d80b3ee5",
                address_uuid=address.pk,
                initiator_ip="198.51.100.8",
                initiator_user_agent="browser",
                request_id="e" * 32,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(initialize)
        assert provider.initiation_entered.wait(timeout=10)
        order = Order.objects.get(user=address.user)
        now = timezone.now()
        Order.objects.filter(pk=order.pk).update(
            created_at=now - timedelta(minutes=20),
            reservation_expires_at=now - timedelta(seconds=1),
        )
        assert expire_unpaid_order(order_id=order.pk).changed is True
        provider.release_initiation.set()
        result = future.result(timeout=20)

    result.payment.refresh_from_db()
    result.order.refresh_from_db()
    product.refresh_from_db()
    assert result.redirect_url is None
    assert result.payment.provider_session_id is not None
    assert result.payment.status == Payment.Status.REDIRECT_READY
    assert result.order.status == Order.Status.CANCELLED
    assert product.stock == 2


def test_race_f_late_verification_and_refund_scheduling_create_one_obligation(settings):
    provider = BlockingVerificationProvider()
    initialized, product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="late-refund-race",
        key="6d08c30e-5046-4f86-a5b5-b9123baa5b05",
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
                provider="late-refund-race",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(verify)
        assert provider.verification_entered.wait(timeout=10)
        second = executor.submit(verify)
        assert second.result(timeout=10).pending is True
        provider.release_verification.set()
        assert first.result(timeout=20).payment.status == Payment.Status.VERIFIED

    initialized.order.refresh_from_db()
    product.refresh_from_db()
    assert initialized.order.status == Order.Status.CANCELLED
    assert product.stock == 2
    assert Refund.objects.filter(payment_id=initialized.payment.pk).count() == 1
    assert Refund.objects.get(payment_id=initialized.payment.pk).reason == Refund.Reason.LATE_PAYMENT


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


def test_race_h1_old_failed_callback_verified_funds_order_once(settings):
    provider = SessionVerificationProvider()
    first, _product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="old-callback",
        key="7c51528e-a854-45b0-a24c-4c7a4d3bb259",
    )
    Payment.objects.filter(pk=first.payment.pk).update(
        status=Payment.Status.FAILED,
        failed_at=timezone.now(),
        failure_code="initiation_rejected",
        operation_token=None,
        operation_started_at=None,
    )
    second = initialization.initialize_payment(
        user=first.order.user,
        idempotency_key="1b8bd6f0-cc3f-4acf-b80b-920797ac937a",
        order_uuid=first.order.uuid,
        initiator_ip="198.51.100.8",
        initiator_user_agent="browser",
        request_id="h" * 32,
    )

    old_result = _verify_in_separate_connection(
        provider_name="old-callback",
        provider_session_id=first.payment.provider_session_id,
    )
    new_result = _verify_in_separate_connection(
        provider_name="old-callback",
        provider_session_id=second.payment.provider_session_id,
    )

    first.payment.refresh_from_db()
    second.payment.refresh_from_db()
    first.order.refresh_from_db()
    assert old_result.payment.applied_to_order_at is not None
    assert new_result.payment.status == Payment.Status.VERIFIED
    assert first.order.status == Order.Status.PROCESSING
    assert Payment.objects.filter(order=first.order, applied_to_order_at__isnull=False).count() == 1
    assert Refund.objects.filter(payment=second.payment, reason=Refund.Reason.DUPLICATE_PAYMENT).count() == 1


def test_race_h2_old_failed_not_paid_callback_cannot_cancel_current_attempt(settings):
    provider = CallbackOutcomeProvider()
    old, current, product = _old_failed_attempt_with_current_open_attempt(
        settings,
        provider,
        provider_name="stale-not-paid",
        key="7dc13c21-a279-4813-8ee2-a04eed178432",
        retry_key="bde4c2fb-9cbd-44b6-aad5-fbff6978a931",
    )
    provider.outcomes[old.payment.provider_session_id] = PaymentVerificationResult(
        outcome=VerificationOutcome.NOT_PAID,
        diagnostic_code="not_paid",
    )

    result = _verify_in_separate_connection(
        provider_name="stale-not-paid",
        provider_session_id=old.payment.provider_session_id,
    )

    old.payment.refresh_from_db()
    current.payment.refresh_from_db()
    old.order.refresh_from_db()
    product.refresh_from_db()
    assert result.payment.status == old.payment.status == Payment.Status.FAILED
    assert current.payment.status in Payment.OPEN_STATUSES
    assert old.order.status == Order.Status.WAITING_FOR_PAYMENT
    assert product.stock == 1
    assert Refund.objects.filter(payment=old.payment).count() == 0


def test_race_h3_old_failed_ambiguous_callback_cannot_reopen_alongside_current_attempt(settings):
    provider = CallbackOutcomeProvider()
    old, current, product = _old_failed_attempt_with_current_open_attempt(
        settings,
        provider,
        provider_name="stale-ambiguous",
        key="9486391e-d2e6-4f70-b03d-b8ea8df9e016",
        retry_key="d4e3a87a-4d60-4d7d-9cf3-5902a40847a2",
    )
    provider.outcomes[old.payment.provider_session_id] = PaymentVerificationResult(
        outcome=VerificationOutcome.AMBIGUOUS,
        diagnostic_code="timeout",
    )

    result = _verify_in_separate_connection(
        provider_name="stale-ambiguous",
        provider_session_id=old.payment.provider_session_id,
    )

    old.payment.refresh_from_db()
    current.payment.refresh_from_db()
    old.order.refresh_from_db()
    product.refresh_from_db()
    assert result.payment.status == old.payment.status == Payment.Status.FAILED
    assert old.payment.status not in Payment.OPEN_STATUSES
    assert current.payment.status in Payment.OPEN_STATUSES
    assert old.order.status == Order.Status.WAITING_FOR_PAYMENT
    assert product.stock == 1


@pytest.mark.parametrize("outcome", [object(), ProviderProtocolError("bad provider result"), ProviderSecurityError("bad signature")])
def test_race_h4_old_failed_provider_failure_cannot_supersede_current_attempt(settings, outcome):
    provider = CallbackOutcomeProvider()
    old, current, product = _old_failed_attempt_with_current_open_attempt(
        settings,
        provider,
        provider_name="stale-provider-failure",
        key="b021e6e5-2c70-42f7-8ba0-cd660d9c9dc6",
        retry_key="e99406a5-bdac-4ee7-81b1-ae8ccfa8143a",
    )
    provider.outcomes[old.payment.provider_session_id] = outcome

    result = _verify_in_separate_connection(
        provider_name="stale-provider-failure",
        provider_session_id=old.payment.provider_session_id,
    )

    old.payment.refresh_from_db()
    current.payment.refresh_from_db()
    old.order.refresh_from_db()
    product.refresh_from_db()
    assert result.payment.status == old.payment.status == Payment.Status.FAILED
    assert old.payment.status not in Payment.OPEN_STATUSES
    assert current.payment.status in Payment.OPEN_STATUSES
    assert old.order.status == Order.Status.WAITING_FOR_PAYMENT
    assert product.stock == 1


def test_race_h5_old_failed_mismatch_refunds_without_cancelling_current_attempt(settings):
    provider = CallbackOutcomeProvider()
    old, current, product = _old_failed_attempt_with_current_open_attempt(
        settings,
        provider,
        provider_name="stale-mismatch",
        key="a2e15bc4-a69a-4983-9c3d-d7d01fdd2728",
        retry_key="7a44e287-4ab4-4128-8e4b-b7fda4815cb3",
    )
    provider.outcomes[old.payment.provider_session_id] = PaymentVerificationResult(
        outcome=VerificationOutcome.VERIFIED,
        provider_transaction_id="transaction-stale-mismatch",
        captured_amount=old.payment.amount + Decimal("1.00"),
        captured_currency="IRT",
    )

    result = _verify_in_separate_connection(
        provider_name="stale-mismatch",
        provider_session_id=old.payment.provider_session_id,
    )

    old.payment.refresh_from_db()
    current.payment.refresh_from_db()
    old.order.refresh_from_db()
    product.refresh_from_db()
    assert result.payment.status == old.payment.status == Payment.Status.VERIFIED
    assert Refund.objects.filter(payment=old.payment, reason=Refund.Reason.AMOUNT_MISMATCH).count() == 1
    assert old.order.status == Order.Status.WAITING_FOR_PAYMENT
    assert product.stock == 1
    assert current.payment.status in Payment.OPEN_STATUSES

    provider.outcomes[current.payment.provider_session_id] = PaymentVerificationResult(
        outcome=VerificationOutcome.VERIFIED,
        provider_transaction_id="transaction-current-match",
        captured_amount=current.payment.amount,
        captured_currency="IRT",
    )
    current_result = _verify_in_separate_connection(
        provider_name="stale-mismatch",
        provider_session_id=current.payment.provider_session_id,
    )

    current.payment.refresh_from_db()
    old.order.refresh_from_db()
    assert current_result.payment.applied_to_order_at is not None
    assert current.payment.applied_to_order_at is not None
    assert old.order.status == Order.Status.PROCESSING


def test_race_i_successful_verify_and_failed_cancellation_never_mix_reservations(settings):
    provider = BlockingVerificationProvider()
    initialized, product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="verify-cancel",
        key="8bc34e51-af43-45da-a0db-9b3d856aa4f0",
    )

    def verify():
        close_old_connections()
        try:
            return verify_payment(
                provider="verify-cancel",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    def cancel():
        close_old_connections()
        try:
            return cancel_failed_payment(order_id=initialized.order.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        verification = executor.submit(verify)
        assert provider.verification_entered.wait(timeout=10)
        cancellation = executor.submit(cancel)
        assert cancellation.result(timeout=10).changed is True
        provider.release_verification.set()
        assert verification.result(timeout=20).payment.status == Payment.Status.VERIFIED

    initialized.order.refresh_from_db()
    initialized.payment.refresh_from_db()
    product.refresh_from_db()
    assert initialized.order.status == Order.Status.CANCELLED
    assert initialized.order.late_payment_detected_at is not None
    assert product.stock == 2
    assert initialized.payment.applied_to_order_at is None
    assert Refund.objects.filter(payment=initialized.payment, reason=Refund.Reason.LATE_PAYMENT).count() == 1


def test_race_j_reconciliation_and_callback_use_one_verification_finalizer(settings):
    provider = BlockingVerificationProvider()
    initialized, _product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="reconcile-callback",
        key="7cd90a09-8fed-4cb6-887e-915559ab7c37",
    )

    def reconcile():
        close_old_connections()
        try:
            return reconcile_payment(payment_id=initialized.payment.pk)
        finally:
            close_old_connections()

    def callback():
        close_old_connections()
        try:
            return verify_payment(
                provider="reconcile-callback",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reconciliation = executor.submit(reconcile)
        assert provider.verification_entered.wait(timeout=10)
        callback_result = executor.submit(callback).result(timeout=10)
        provider.release_verification.set()
        reconciliation_result = reconciliation.result(timeout=20)

    initialized.payment.refresh_from_db()
    initialized.order.refresh_from_db()
    assert callback_result.pending is True
    assert reconciliation_result.payment.status == Payment.Status.VERIFIED
    assert initialized.payment.callback_count == 1
    assert initialized.payment.applied_to_order_at is not None
    assert initialized.order.status == Order.Status.PROCESSING
    assert provider.verify_calls == 1


def test_race_k_payment_protects_order_from_deletion_after_creation(settings):
    provider = BlockingInitializationProvider()
    register_provider("payment-protect", provider)
    settings.PAYMENT_PROVIDER = "payment-protect"
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    address = AddressFactory()
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=ProductFactory(stock=2, price=Decimal("100.00"), discount_price=None), quantity=1)

    def initialize():
        close_old_connections()
        try:
            return initialization.initialize_payment(
                user=CustomUser.objects.get(pk=address.user_id),
                idempotency_key="326570fa-b11d-43e3-88dc-4e523d5ec1e9",
                address_uuid=address.pk,
                initiator_ip="198.51.100.8",
                initiator_user_agent="browser",
                request_id="k" * 32,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as executor:
        payment_future = executor.submit(initialize)
        assert provider.initiation_entered.wait(timeout=10)
        order = Order.objects.get(user=address.user)
        with pytest.raises(ProtectedError):
            order.delete()
        provider.release_initiation.set()
        result = payment_future.result(timeout=20)

    assert Payment.objects.filter(pk=result.payment.pk, order_id=result.order.pk).exists()
    assert Order.objects.filter(pk=result.order.pk).exists()


def test_race_l_refund_execution_cannot_overwrite_manual_resolution():
    provider = BlockingRefundProvider()
    register_provider("refund-manual-race", provider)
    refund = RefundFactory(
        provider="refund-manual-race",
        payment__provider="refund-manual-race",
    )
    superuser = CustomUser.objects.create_superuser(
        phone_number="09129999999",
        email="refund-admin@example.test",
        password="safe-password-123",
    )
    Refund.objects.filter(pk=refund.pk).update(
        status=Refund.Status.MANUAL_REVIEW,
        manual_review_at=timezone.now(),
        failure_code="manual_required",
    )

    def execute():
        close_old_connections()
        try:
            return execute_refund(refund_id=refund.pk)
        finally:
            close_old_connections()

    def complete_manually():
        close_old_connections()
        try:
            return record_manual_refund_completion(
                refund_id=refund.pk,
                completed_by=CustomUser.objects.get(pk=superuser.pk),
                provider_refund_id="manual-refund-identity",
                confirmed=True,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        execution = executor.submit(execute)
        assert provider.refund_entered.wait(timeout=10)
        manual = executor.submit(complete_manually)
        with pytest.raises(RefundNotEligibleError):
            manual.result(timeout=10)
        provider.release_refund.set()
        assert execution.result(timeout=20).status == Refund.Status.REFUNDED

    refund.refresh_from_db()
    assert refund.status == Refund.Status.REFUNDED
    assert refund.provider_refund_id == "refund-blocking"
    assert refund.completed_by is None
    assert provider.refund_calls == 1


def test_race_m_provider_transaction_identity_cannot_apply_to_two_orders(settings):
    provider = BarrierVerificationProvider(parties=2, transaction_id="shared-provider-transaction")
    first, _first_product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="transaction-conflict",
        key="765b5d74-ff83-4c01-86e2-574882420466",
    )
    second, _second_product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="transaction-conflict",
        key="facd35cc-d472-477a-90dd-d0713f4ef6b1",
    )

    def verify(payment):
        close_old_connections()
        try:
            return verify_payment(
                provider="transaction-conflict",
                provider_session_id=payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in (
                executor.submit(verify, first.payment),
                executor.submit(verify, second.payment),
            )
        ]

    first.payment.refresh_from_db()
    second.payment.refresh_from_db()
    first.order.refresh_from_db()
    second.order.refresh_from_db()
    assert provider.verify_calls == 2
    assert Payment.objects.filter(provider="transaction-conflict", provider_transaction_id="shared-provider-transaction").count() == 1
    assert [first.payment.status, second.payment.status].count(Payment.Status.VERIFIED) == 1
    assert [first.payment.status, second.payment.status].count(Payment.Status.MANUAL_REVIEW) == 1
    assert [first.order.status, second.order.status].count(Order.Status.PROCESSING) == 1
    assert Payment.objects.filter(applied_to_order_at__isnull=False).count() == 1
    assert any(result.payment.status == Payment.Status.MANUAL_REVIEW for result in results)


def test_race_n_amount_mismatch_and_expiry_create_one_mismatch_refund(settings):
    provider = BlockingVerificationProvider()
    initialized, product = _checkout_and_initialize(
        settings,
        provider,
        provider_name="mismatch-expiry",
        key="794d536d-a807-474d-a95a-6a66d2ee436d",
    )
    original_verify = provider.verify_payment

    def mismatched_verify(**kwargs):
        verified = original_verify(**kwargs)
        return PaymentVerificationResult(
            outcome=verified.outcome,
            provider_transaction_id=verified.provider_transaction_id,
            captured_amount=kwargs["expected_amount"] + Decimal("1.00"),
            captured_currency=kwargs["expected_currency"],
        )

    provider.verify_payment = mismatched_verify

    def verify():
        close_old_connections()
        try:
            return verify_payment(
                provider="mismatch-expiry",
                provider_session_id=initialized.payment.provider_session_id,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as executor:
        verification = executor.submit(verify)
        assert provider.verification_entered.wait(timeout=10)
        now = timezone.now()
        Order.objects.filter(pk=initialized.order.pk).update(
            created_at=now - timedelta(minutes=20),
            reservation_expires_at=now - timedelta(seconds=1),
        )
        assert expire_unpaid_order(order_id=initialized.order.pk).changed is True
        provider.release_verification.set()
        assert verification.result(timeout=20).payment.status == Payment.Status.VERIFIED

    initialized.payment.refresh_from_db()
    initialized.order.refresh_from_db()
    product.refresh_from_db()
    assert initialized.payment.captured_amount == initialized.payment.amount + Decimal("1.00")
    assert initialized.order.status == Order.Status.CANCELLED
    assert product.stock == 2
    assert Refund.objects.filter(payment=initialized.payment, reason=Refund.Reason.AMOUNT_MISMATCH).count() == 1
