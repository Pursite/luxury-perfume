from datetime import timedelta
from decimal import Decimal
import logging

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.test import override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.lib.loggers import activity_logger
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import create_waiting_order
from apps.payments.models import Payment, Refund
from apps.payments.exceptions import (
    PaymentEligibilityError,
    PaymentProviderProtocolError,
    PaymentProviderUnavailableError,
    RefundNotEligibleError,
)
from apps.payments.exceptions import ProviderProtocolError, ProviderSecurityError, ProviderTransportError
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    PaymentVerificationResult,
    RefundOutcome,
    RefundResult,
    VerificationOutcome,
)
from apps.payments.providers.registry import register_provider
from apps.payments.services.initialization import initialize_payment
from apps.payments.services.refunds import execute_refund, record_manual_refund_completion
from apps.payments.services.verification import verify_payment
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory
from apps.payments.tests.factories import RefundFactory


pytestmark = pytest.mark.django_db


class _AuditHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class FakeProvider:
    def __init__(self):
        self.create_calls = 0
        self.verify_calls = 0
        self.refund_calls = 0
        self.initiation = PaymentInitiationResult(
            outcome=InitiationOutcome.READY,
            provider_session_id="session-1",
            redirect_url="https://gateway.example.test/pay/session-1",
        )
        self.verification = PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="transaction-1",
            provider_receipt_id="receipt-1",
            captured_amount=Decimal("100.00"),
            captured_currency="IRT",
        )
        self.refund = RefundResult(
            outcome=RefundOutcome.REFUNDED,
            provider_refund_id="refund-1",
            provider_receipt_id="refund-receipt-1",
        )

    def create_payment(self, **kwargs):
        self.create_calls += 1
        assert Payment.objects.filter(uuid=kwargs["payment_uuid"]).exists()
        return self.initiation

    def verify_payment(self, **kwargs):
        self.verify_calls += 1
        if isinstance(self.verification, Exception):
            raise self.verification
        return self.verification

    def refund_payment(self, **kwargs):
        self.refund_calls += 1
        if isinstance(self.refund, Exception):
            raise self.refund
        return self.refund

    def build_redirect_url(self, provider_session_id):
        return f"https://gateway.example.test/pay/{provider_session_id}"


@pytest.fixture
def provider(settings):
    adapter = FakeProvider()
    register_provider("fake-payments", adapter)
    settings.PAYMENT_PROVIDER = "fake-payments"
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    return adapter


def _checkout():
    address = AddressFactory()
    product = ProductFactory(stock=3, price=Decimal("100.00"), discount_price=None)
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return address, product


def _initialize(provider, *, key="639d5086-942d-475a-b2ac-7694cc1bdebb"):
    address, product = _checkout()
    result = initialize_payment(
        user=address.user,
        idempotency_key=key,
        address_uuid=address.pk,
        initiator_ip="198.51.100.8",
        initiator_user_agent="browser",
        request_id="a" * 32,
    )
    return result, product


def test_initialization_emits_allowlisted_financial_audit_event(provider):
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        result, _product = _initialize(provider)
    finally:
        activity_logger.removeHandler(handler)

    record = next(record for record in handler.records if record.event == "payment_initialized")
    assert record.payment_uuid == str(result.payment.uuid)
    assert record.order_uuid == str(result.order.uuid)
    assert record.provider == "fake-payments"
    for forbidden in (
        "initiator_ip", "callback_ip", "user_agent", "provider_session_id",
        "provider_transaction_id", "provider_refund_id", "raw_payload",
    ):
        assert not hasattr(record, forbidden)


def test_verification_emits_callback_and_success_audit_events(provider):
    initialized, _product = _initialize(provider)
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        verify_payment(
            provider="fake-payments",
            provider_session_id=initialized.payment.provider_session_id,
            callback_ip="203.0.113.8",
        )
    finally:
        activity_logger.removeHandler(handler)

    assert {record.event for record in handler.records} >= {
        "payment_callback_received",
        "payment_verification_succeeded",
    }


def test_provider_security_failure_emits_error_and_manual_review_audit_events(provider):
    initialized, _product = _initialize(provider)
    provider.verification = ProviderSecurityError("untrusted provider response")
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        verify_payment(
            provider="fake-payments",
            provider_session_id=initialized.payment.provider_session_id,
        )
    finally:
        activity_logger.removeHandler(handler)

    assert {record.event for record in handler.records} >= {
        "payment_provider_error",
        "payment_manual_review_required",
    }


def test_provider_transport_failure_emits_safe_error_and_ambiguous_audit_events(provider):
    initialized, _product = _initialize(provider)
    provider.verification = ProviderTransportError("gateway timeout details must not be logged")
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        result = verify_payment(
            provider="fake-payments",
            provider_session_id=initialized.payment.provider_session_id,
        )
    finally:
        activity_logger.removeHandler(handler)

    assert result.pending is True
    assert {record.event for record in handler.records} >= {"payment_provider_error"}
    error = next(record for record in handler.records if record.event == "payment_provider_error")
    assert error.outcome == "transport"
    assert "gateway timeout" not in error.getMessage()


def test_negative_verification_emits_failed_audit_event(provider):
    initialized, _product = _initialize(provider)
    provider.verification = PaymentVerificationResult(
        outcome=VerificationOutcome.NOT_PAID,
        diagnostic_code="not_paid",
    )
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        verify_payment(
            provider="fake-payments",
            provider_session_id=initialized.payment.provider_session_id,
        )
    finally:
        activity_logger.removeHandler(handler)

    assert "payment_verification_failed" in {record.event for record in handler.records}


def test_late_verification_emits_late_and_refund_queued_audit_events(provider):
    initialized, _product = _initialize(provider)
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            verify_payment(
                provider="fake-payments",
                provider_session_id=initialized.payment.provider_session_id,
            )
    finally:
        activity_logger.removeHandler(handler)

    assert {record.event for record in handler.records} >= {
        "payment_late",
        "refund_queued",
    }


def test_refund_resolution_emits_success_retry_and_manual_review_audit_events(provider):
    succeeded = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    retry = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    review = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    handler = _AuditHandler()
    activity_logger.addHandler(handler)
    try:
        execute_refund(refund_id=succeeded.pk)
        provider.refund = RefundResult(outcome=RefundOutcome.AMBIGUOUS, diagnostic_code="timeout")
        execute_refund(refund_id=retry.pk)
        provider.refund = ProviderProtocolError("malformed response")
        execute_refund(refund_id=review.pk)
    finally:
        activity_logger.removeHandler(handler)

    assert {record.event for record in handler.records} >= {
        "refund_succeeded",
        "refund_retry_scheduled",
        "refund_manual_review_required",
    }


def test_initialization_commits_intent_before_provider_call_and_replays_same_key(provider):
    first, product = _initialize(provider)
    replay = initialize_payment(
        user=first.order.user,
        idempotency_key=first.payment.idempotency_key,
        address_uuid=first.order.source_address_uuid,
        initiator_ip="198.51.100.9",
        initiator_user_agent="changed-browser",
        request_id="b" * 32,
    )

    product.refresh_from_db()
    assert first.created is True
    assert replay.created is False
    assert first.payment.pk == replay.payment.pk
    assert first.redirect_url == "https://gateway.example.test/pay/session-1"
    assert first.payment.amount == first.order.total == Decimal("100.00")
    assert first.payment.next_reconciliation_at is not None
    assert provider.create_calls == 1
    assert product.stock == 2


def test_initialization_sanitizes_and_bounds_user_agent_evidence(provider):
    address, _product = _checkout()

    result = initialize_payment(
        user=address.user,
        idempotency_key="15092693-f63d-4805-b791-8f08ea8aff27",
        address_uuid=address.pk,
        initiator_ip="198.51.100.8",
        initiator_user_agent="browser\nwith\x00controls" + ("x" * 600),
        request_id="a" * 32,
    )

    assert "\n" not in result.payment.initiator_user_agent
    assert "\x00" not in result.payment.initiator_user_agent
    assert len(result.payment.initiator_user_agent) <= 512


@pytest.mark.parametrize("initiator_ip", (None, "", "not-an-ip", "198.51.100.8/24"))
def test_initialization_rejects_untrusted_or_malformed_ip_before_checkout(provider, initiator_ip):
    address, product = _checkout()

    with pytest.raises(PaymentEligibilityError):
        initialize_payment(
            user=address.user,
            idempotency_key="71692c3f-4805-4fe6-aeaa-ab07de2e73e3",
            address_uuid=address.pk,
            initiator_ip=initiator_ip,
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    product.refresh_from_db()
    assert Payment.objects.count() == 0
    assert Order.objects.filter(user=address.user).count() == 0
    assert CartItem.objects.filter(cart__user=address.user).count() == 1
    assert product.stock == 3
    assert provider.create_calls == 0


def test_initialization_canonicalizes_trusted_ip_evidence(provider):
    address, _product = _checkout()

    result = initialize_payment(
        user=address.user,
        idempotency_key="9d8fd0b9-715a-4f7f-a401-b2e2d89aeea2",
        address_uuid=address.pk,
        initiator_ip="2001:0db8:0:0:0:0:0:1",
        initiator_user_agent="browser",
        request_id="a" * 32,
    )

    assert result.payment.initiator_ip == "2001:db8::1"


def test_ambiguous_initialization_remains_reconcilable(provider):
    provider.initiation = PaymentInitiationResult(outcome=InitiationOutcome.AMBIGUOUS, diagnostic_code="timeout")

    result, _product = _initialize(provider, key="c21bfd9c-a6e9-45e1-b3b4-590905af5134")

    result.payment.refresh_from_db()
    assert result.pending is True
    assert result.redirect_url is None
    assert result.payment.status == Payment.Status.PENDING
    assert result.payment.next_reconciliation_at is not None


def test_unsafe_provider_redirect_releases_lease_into_manual_review(provider):
    provider.initiation = PaymentInitiationResult(
        outcome=InitiationOutcome.READY,
        provider_session_id="unsafe-session",
        redirect_url="https://attacker.example.test/pay",
    )
    address, _product = _checkout()
    key = "c4435653-0711-4808-abd9-df13afe2c792"

    with pytest.raises(PaymentProviderProtocolError):
        initialize_payment(
            user=address.user,
            idempotency_key=key,
            address_uuid=address.pk,
            initiator_ip="198.51.100.8",
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    payment = Payment.objects.get(idempotency_key=key)
    assert payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.operation_token is None


def test_duplicate_provider_session_becomes_manual_review(provider):
    _first, _product = _initialize(provider, key="437d702e-8276-4b94-a13c-a5bf9aef1df1")

    second, _product = _initialize(provider, key="9c7672eb-d6a7-47f1-9a2d-f370323f0024")

    second.payment.refresh_from_db()
    assert second.pending is True
    assert second.redirect_url is None
    assert second.payment.status == Payment.Status.MANUAL_REVIEW
    assert second.payment.operation_token is None


def test_malformed_initiation_result_releases_lease(provider):
    provider.initiation = object()
    address, _product = _checkout()
    key = "56efeaae-379a-473a-bbc2-b394277b18d2"

    with pytest.raises(PaymentProviderProtocolError):
        initialize_payment(
            user=address.user,
            idempotency_key=key,
            address_uuid=address.pk,
            initiator_ip="198.51.100.8",
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    payment = Payment.objects.get(idempotency_key=key)
    assert payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.operation_token is None


def test_overlong_initiation_identity_releases_lease(provider):
    provider.initiation = PaymentInitiationResult(
        outcome=InitiationOutcome.READY,
        provider_session_id="s" * 256,
        redirect_url="https://gateway.example.test/pay/session",
    )
    address, _product = _checkout()
    key = "d50b38ac-ab1e-466b-9247-f6bba9bf8c1f"

    with pytest.raises(PaymentProviderProtocolError):
        initialize_payment(
            user=address.user,
            idempotency_key=key,
            address_uuid=address.pk,
            initiator_ip="198.51.100.8",
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    payment = Payment.objects.get(idempotency_key=key)
    assert payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.operation_token is None


def test_missing_runtime_provider_keeps_initiation_reconcilable(settings):
    settings.PAYMENT_PROVIDER = "missing-runtime-provider"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    address, _product = _checkout()
    key = "461977cd-68d8-49cc-9d8e-c037b9699ce7"

    with pytest.raises(PaymentProviderUnavailableError):
        initialize_payment(
            user=address.user,
            idempotency_key=key,
            address_uuid=address.pk,
            initiator_ip="198.51.100.8",
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    payment = Payment.objects.get(idempotency_key=key)
    assert payment.status == Payment.Status.PENDING
    assert payment.operation_token is None
    assert payment.next_reconciliation_at is not None


def test_matching_verified_payment_funds_order_once(provider):
    initialized, product = _initialize(provider, key="ac85fd62-7c27-482f-8983-fd72d5859cae")

    first = verify_payment(provider="fake-payments", provider_session_id="session-1", callback_ip="203.0.113.5")
    second = verify_payment(provider="fake-payments", provider_session_id="session-1", callback_ip="203.0.113.5")

    initialized.payment.refresh_from_db()
    initialized.order.refresh_from_db()
    product.refresh_from_db()
    assert first.payment.status == second.payment.status == Payment.Status.VERIFIED
    assert initialized.payment.applied_to_order_at is not None
    assert initialized.order.status == Order.Status.PROCESSING
    assert initialized.order.items.get().reservation.status == StockReservation.Status.CONSUMED
    assert Refund.objects.count() == 0
    assert provider.verify_calls == 1
    assert product.stock == 2


def test_late_capture_is_verified_and_creates_one_refund(provider, mocker):
    initialized, product = _initialize(provider, key="53c1d98c-36a8-42b0-baaa-820147454c3e")
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )
    mocker.patch("apps.payments.tasks.execute_refund_task.delay")

    result = verify_payment(provider="fake-payments", provider_session_id="session-1", callback_ip="203.0.113.5")

    initialized.order.refresh_from_db()
    product.refresh_from_db()
    refund = Refund.objects.get(payment=result.payment)
    assert result.payment.status == Payment.Status.VERIFIED
    assert initialized.order.status == Order.Status.CANCELLED
    assert refund.reason == Refund.Reason.LATE_PAYMENT
    assert refund.amount == Decimal("100.00")
    assert product.stock == 3


def test_amount_mismatch_never_funds_order_and_has_reason_precedence(provider, mocker):
    initialized, _product = _initialize(provider, key="5347f749-cb8a-4d94-b8f7-a13ed2bd990c")
    provider.verification = PaymentVerificationResult(
        outcome=VerificationOutcome.VERIFIED,
        provider_transaction_id="transaction-mismatch",
        captured_amount=Decimal("90.00"),
        captured_currency="IRT",
    )
    mocker.patch("apps.payments.tasks.execute_refund_task.delay")

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.order.refresh_from_db()
    refund = Refund.objects.get(payment=result.payment)
    assert initialized.order.status == Order.Status.CANCELLED
    assert result.payment.applied_to_order_at is None
    assert refund.reason == Refund.Reason.AMOUNT_MISMATCH


def test_captured_currency_mismatch_preserves_truth_and_refund_obligation(provider, mocker):
    initialized, _product = _initialize(provider, key="9547f4e8-785c-4372-b106-b292f1d64405")
    provider.verification = PaymentVerificationResult(
        outcome=VerificationOutcome.VERIFIED,
        provider_transaction_id="transaction-currency-mismatch",
        captured_amount=Decimal("100.00"),
        captured_currency="IRR",
    )
    mocker.patch("apps.payments.tasks.execute_refund_task.delay")

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    refund = Refund.objects.get(payment=result.payment)
    assert result.payment.status == Payment.Status.VERIFIED
    assert result.payment.captured_currency == "IRR"
    assert refund.reason == Refund.Reason.AMOUNT_MISMATCH
    assert refund.currency == "IRR"


def test_definitive_no_payment_cancels_redirected_order(provider):
    initialized, product = _initialize(provider, key="a29bec2e-ec7b-454d-9fdc-73bf6fa78e15")
    provider.verification = PaymentVerificationResult(
        outcome=VerificationOutcome.NOT_PAID,
        diagnostic_code="not_paid",
    )

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.order.refresh_from_db()
    product.refresh_from_db()
    assert result.payment.status == Payment.Status.FAILED
    assert initialized.order.status == Order.Status.CANCELLED
    assert product.stock == 3


def test_malformed_positive_verification_returns_to_reconciliation(provider):
    initialized, _product = _initialize(provider, key="15fc32ea-30f3-403c-ac9f-cfa0d6bb57a9")
    provider.verification = PaymentVerificationResult(
        outcome=VerificationOutcome.VERIFIED,
        provider_transaction_id=None,
        captured_amount=Decimal("100.00"),
        captured_currency="IRT",
    )

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.payment.refresh_from_db()
    assert result.pending is True
    assert initialized.payment.status == Payment.Status.REDIRECT_READY
    assert initialized.payment.operation_token is None
    assert initialized.payment.next_reconciliation_at is not None


def test_provider_protocol_failure_releases_verification_lease(provider):
    initialized, _product = _initialize(provider, key="8ecee696-ddc1-4757-bc60-0f5bef7b2b8f")
    provider.verification = ProviderProtocolError("raw provider details")

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.payment.refresh_from_db()
    assert result.pending is True
    assert initialized.payment.status == Payment.Status.REDIRECT_READY
    assert initialized.payment.operation_token is None
    assert initialized.payment.failure_code == "verification_protocol"


def test_malformed_verification_result_returns_to_reconciliation(provider):
    initialized, _product = _initialize(provider, key="c284ffb0-6fa2-4cf1-8ee8-cb6b8419d8ec")
    provider.verification = object()

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.payment.refresh_from_db()
    assert result.pending is True
    assert initialized.payment.status == Payment.Status.REDIRECT_READY
    assert initialized.payment.operation_token is None


@pytest.mark.parametrize(
    "verification",
    [
        PaymentVerificationResult(
            outcome="unknown",
            provider_transaction_id="transaction-unknown",
            captured_amount=Decimal("100.00"),
            captured_currency="IRT",
        ),
        PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="t" * 256,
            captured_amount=Decimal("100.00"),
            captured_currency="IRT",
        ),
        PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="transaction-too-large",
            captured_amount=Decimal("1e30"),
            captured_currency="IRT",
        ),
    ],
)
def test_invalid_capture_fields_never_verify_payment(provider, verification):
    initialized, _product = _initialize(
        provider,
        key="93269abc-f995-4b72-85c1-c2373bb7ff2a",
    )
    provider.verification = verification

    result = verify_payment(provider="fake-payments", provider_session_id="session-1")

    initialized.payment.refresh_from_db()
    initialized.order.refresh_from_db()
    assert result.pending is True
    assert initialized.payment.status == Payment.Status.REDIRECT_READY
    assert initialized.payment.operation_token is None
    assert initialized.order.status == Order.Status.WAITING_FOR_PAYMENT


def test_duplicate_provider_transaction_moves_conflicting_attempt_to_review(provider):
    first, _ = _initialize(provider, key="6128d51d-ef3a-42e1-9eb6-1576b359e51a")
    verify_payment(provider="fake-payments", provider_session_id="session-1")
    provider.initiation = PaymentInitiationResult(
        outcome=InitiationOutcome.READY,
        provider_session_id="session-2",
        redirect_url="https://gateway.example.test/pay/session-2",
    )
    second, _ = _initialize(provider, key="7bb005bf-b71b-423e-894b-d8d8f6abeaa7")

    result = verify_payment(provider="fake-payments", provider_session_id="session-2")

    second.payment.refresh_from_db()
    second.order.refresh_from_db()
    assert result.payment.status == Payment.Status.MANUAL_REVIEW
    assert second.payment.operation_token is None
    assert second.order.status == Order.Status.WAITING_FOR_PAYMENT
    assert Payment.objects.get(pk=first.payment.pk).applied_to_order_at is not None


def test_refund_execution_is_idempotent(provider):
    initialized, _product = _initialize(provider, key="972a69cc-6384-4439-84ba-78e3aebd955d")
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )
    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        verified = verify_payment(provider="fake-payments", provider_session_id="session-1")
    refund = Refund.objects.get(payment=verified.payment)

    first = execute_refund(refund_id=refund.pk)
    second = execute_refund(refund_id=refund.pk)

    assert first.status == second.status == Refund.Status.REFUNDED
    assert provider.refund_calls == 1


def test_ambiguous_refund_moves_to_manual_review_after_five_attempts(provider):
    initialized, _product = _initialize(provider, key="8f6b39d6-078b-4bd4-a8b5-e297f3281927")
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=expired_at - timedelta(minutes=15),
        reservation_expires_at=expired_at,
    )
    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        verified = verify_payment(provider="fake-payments", provider_session_id="session-1")
    refund = Refund.objects.get(payment=verified.payment)
    provider.refund = RefundResult(outcome=RefundOutcome.AMBIGUOUS, diagnostic_code="timeout")

    for _ in range(5):
        refund = execute_refund(refund_id=refund.pk)

    assert refund.status == Refund.Status.MANUAL_REVIEW
    assert refund.attempt_count == 5
    assert provider.refund_calls == 5


def test_refund_protocol_failure_becomes_manual_review(provider):
    initialized, _product = _initialize(provider, key="cffc2227-f802-4c1a-8c08-928e4db3a85f")
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=initialized.order.pk).update(
        created_at=expired_at - timedelta(minutes=15), reservation_expires_at=expired_at
    )
    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        verified = verify_payment(provider="fake-payments", provider_session_id="session-1")
    refund = Refund.objects.get(payment=verified.payment)
    provider.refund = ProviderProtocolError("raw provider details")

    result = execute_refund(refund_id=refund.pk)

    assert result.status == Refund.Status.MANUAL_REVIEW
    assert result.operation_token is None


def test_duplicate_provider_refund_identity_becomes_manual_review(provider):
    first = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    second = RefundFactory(provider="fake-payments", payment__provider="fake-payments")

    execute_refund(refund_id=first.pk)
    result = execute_refund(refund_id=second.pk)

    assert result.status == Refund.Status.MANUAL_REVIEW
    assert result.operation_token is None
    assert result.failure_code == "refund_identity_conflict"


def test_malformed_refund_result_becomes_manual_review(provider):
    refund = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    provider.refund = object()

    result = execute_refund(refund_id=refund.pk)

    assert result.status == Refund.Status.MANUAL_REVIEW
    assert result.operation_token is None


def test_overlong_refund_identity_becomes_manual_review(provider):
    refund = RefundFactory(provider="fake-payments", payment__provider="fake-payments")
    provider.refund = RefundResult(
        outcome=RefundOutcome.REFUNDED,
        provider_refund_id="r" * 256,
    )

    result = execute_refund(refund_id=refund.pk)

    assert result.status == Refund.Status.MANUAL_REVIEW
    assert result.failure_code == "refund_provider_protocol"
    assert result.operation_token is None


def test_missing_runtime_provider_moves_refund_to_manual_review():
    refund = RefundFactory(provider="missing-refund-provider", payment__provider="missing-refund-provider")

    result = execute_refund(refund_id=refund.pk)

    assert result.status == Refund.Status.MANUAL_REVIEW
    assert result.failure_code == "refund_provider_unavailable"
    assert result.operation_token is None


def test_superuser_can_record_one_confirmed_external_refund_completion():
    operator = UserFactory(is_staff=True, is_superuser=True)
    refund = RefundFactory(
        status=Refund.Status.MANUAL_REVIEW,
        manual_review_at=timezone.now(),
        failure_code="provider_rejected",
        next_retry_at=None,
    )

    result = record_manual_refund_completion(
        refund_id=refund.pk,
        completed_by=operator,
        provider_refund_id="external-refund-1",
        confirmed=True,
    )

    assert result.status == Refund.Status.REFUNDED
    assert result.completed_by == operator
    assert result.provider_refund_id == "external-refund-1"
    assert result.refunded_at is not None
    assert LogEntry.objects.filter(
        user=operator,
        object_id=str(refund.pk),
        action_flag=CHANGE,
    ).exists()


@pytest.mark.parametrize("confirmed", [False, True])
def test_manual_refund_completion_requires_superuser_and_explicit_confirmation(confirmed):
    operator = UserFactory(is_staff=True, is_superuser=confirmed is False)
    refund = RefundFactory(
        status=Refund.Status.MANUAL_REVIEW,
        manual_review_at=timezone.now(),
        failure_code="provider_rejected",
        next_retry_at=None,
    )

    with pytest.raises(RefundNotEligibleError):
        record_manual_refund_completion(
            refund_id=refund.pk,
            completed_by=operator,
            provider_refund_id="external-refund-2",
            confirmed=confirmed,
        )


def test_expired_existing_order_is_durably_reconciled_before_conflict(provider):
    address, product = _checkout()
    order, _ = create_waiting_order(
        user=address.user,
        address_id=address.pk,
        idempotency_key="5cb07700-509c-445b-97c5-413526bddf5f",
    )
    expired_at = timezone.now() - timedelta(seconds=1)
    Order.objects.filter(pk=order.pk).update(
        created_at=expired_at - timedelta(minutes=15), reservation_expires_at=expired_at
    )

    with pytest.raises(PaymentEligibilityError):
        initialize_payment(
            user=address.user,
            idempotency_key="29682720-0a07-4890-aaf0-2ff6c2850bcc",
            order_uuid=order.uuid,
            initiator_ip="198.51.100.8",
            initiator_user_agent="browser",
            request_id="a" * 32,
        )

    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert product.stock == 3
