import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.payments.models import Payment, Refund
from apps.payments.tests.factories import PaymentFactory, RefundFactory


pytestmark = pytest.mark.django_db


def test_payment_uses_internal_key_and_immutable_public_uuid():
    payment = PaymentFactory()

    assert isinstance(payment.pk, int)
    assert payment.uuid is not None
    assert Payment._meta.get_field("uuid").editable is False


def test_database_prevents_two_open_attempts_for_one_order():
    first = PaymentFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentFactory(order=first.order)


def test_verified_payment_requires_complete_capture_identity():
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentFactory(status=Payment.Status.VERIFIED, verified_at=timezone.now())


def test_manual_review_payment_cannot_have_automatic_reconciliation_work():
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentFactory(
            status=Payment.Status.MANUAL_REVIEW,
            manual_review_at=timezone.now(),
            failure_code="provider_security",
            next_reconciliation_at=timezone.now(),
        )


def test_provider_transaction_identity_is_unique_per_provider():
    first = PaymentFactory(
        status=Payment.Status.VERIFIED,
        provider_session_id="session-one",
        provider_transaction_id="transaction-one",
        captured_amount="100.00",
        captured_currency="IRT",
        redirect_ready_at=timezone.now(),
        verified_at=timezone.now(),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentFactory(
            status=Payment.Status.VERIFIED,
            provider_session_id="session-two",
            provider_transaction_id=first.provider_transaction_id,
            captured_amount="100.00",
            captured_currency="IRT",
            redirect_ready_at=timezone.now(),
            verified_at=timezone.now(),
        )


def test_database_allows_only_one_refund_obligation_per_payment():
    refund = RefundFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        RefundFactory(payment=refund.payment)


def test_refunded_state_requires_completion_evidence():
    with pytest.raises(IntegrityError), transaction.atomic():
        RefundFactory(status=Refund.Status.REFUNDED, refunded_at=timezone.now())
