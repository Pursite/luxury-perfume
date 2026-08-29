from datetime import timedelta
import pytest
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.services.checkout import create_waiting_order
from apps.payments.models import Payment
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    PaymentVerificationResult,
    VerificationOutcome,
)
from apps.payments.providers.registry import register_provider
from apps.payments.services.reconciliation import reconcile_payment
from apps.payments.services.reconciliation import rearm_manual_review_payment
from apps.payments.tasks import (
    scrub_expired_payment_audit_metadata,
    sweep_pending_refunds,
    sweep_reconcilable_payments,
)
from apps.payments.tests.factories import PaymentFactory, RefundFactory
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class ReconcileProvider:
    def verify_payment(self, **kwargs):
        return PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="transaction-reconcile",
            captured_amount=kwargs["expected_amount"],
            captured_currency="IRT",
        )


class LookupProvider:
    def lookup_payment(self, **kwargs):
        return PaymentInitiationResult(
            outcome=InitiationOutcome.READY,
            provider_session_id="session-recovered",
            redirect_url="https://gateway.example.test/pay/session-recovered",
        )


class MalformedLookupProvider:
    def lookup_payment(self, **kwargs):
        return object()


class NeverCallProvider:
    def verify_payment(self, **kwargs):
        raise AssertionError("Manual-review payments must not be verified automatically.")


def test_reconciliation_uses_canonical_verifier_without_forging_callback_evidence():
    register_provider("reconcile", ReconcileProvider())
    address = AddressFactory()
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=ProductFactory(stock=2, price="100.00", discount_price=None), quantity=1)
    order, _ = create_waiting_order(
        user=address.user,
        address_id=address.pk,
        idempotency_key="d0f8577f-9225-494c-879e-0e790a482450",
    )
    payment = PaymentFactory(
        order=order,
        provider="reconcile",
        status=Payment.Status.REDIRECT_READY,
        provider_session_id="session-reconcile",
        redirect_ready_at=timezone.now(),
        next_reconciliation_at=timezone.now(),
    )

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.payment.status == Payment.Status.VERIFIED
    assert payment.callback_count == 0
    assert payment.first_callback_at is None
    assert payment.reconciliation_attempts == 1
    assert payment.last_reconciled_at is not None


def test_sweepers_queue_only_due_durable_records(mocker):
    due_payment = PaymentFactory(next_reconciliation_at=timezone.now() - timedelta(seconds=1))
    PaymentFactory(next_reconciliation_at=timezone.now() + timedelta(minutes=1))
    due_refund = RefundFactory(next_retry_at=timezone.now() - timedelta(seconds=1))
    RefundFactory(next_retry_at=timezone.now() + timedelta(minutes=1))
    reconcile_delay = mocker.patch("apps.payments.tasks.reconcile_payment_task.delay")
    refund_delay = mocker.patch("apps.payments.tasks.execute_refund_task.delay")

    payment_count = sweep_reconcilable_payments()
    refund_count = sweep_pending_refunds()

    assert payment_count == refund_count == 1
    reconcile_delay.assert_called_once_with(due_payment.pk)
    refund_delay.assert_called_once_with(due_refund.pk)


def test_reconciliation_sweeper_never_queues_manual_review_payment(mocker):
    manual_review = PaymentFactory(
        status=Payment.Status.MANUAL_REVIEW,
        manual_review_at=timezone.now(),
        failure_code="provider_security",
    )
    reconcile_delay = mocker.patch("apps.payments.tasks.reconcile_payment_task.delay")

    count = sweep_reconcilable_payments()

    assert count == 0
    reconcile_delay.assert_not_called()
    manual_review.refresh_from_db()
    assert manual_review.status == Payment.Status.MANUAL_REVIEW
    assert manual_review.status not in Payment.RECONCILABLE_STATUSES


def test_direct_reconciliation_task_never_resumes_manual_review_payment():
    register_provider("manual-review", NeverCallProvider())
    payment = PaymentFactory(
        provider="manual-review",
        status=Payment.Status.MANUAL_REVIEW,
        provider_session_id="manual-session",
        redirect_ready_at=timezone.now(),
        manual_review_at=timezone.now(),
        failure_code="provider_security",
    )

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.operation_token is None
    assert payment.next_reconciliation_at is None


def test_superuser_can_explicitly_rearm_manual_review_payment():
    payment = PaymentFactory(
        status=Payment.Status.MANUAL_REVIEW,
        manual_review_at=timezone.now(),
        failure_code="provider_security",
    )
    operator = UserFactory(is_staff=True, is_superuser=True)

    rearmed = rearm_manual_review_payment(
        payment_id=payment.pk,
        requested_by=operator,
    )

    assert rearmed.status == Payment.Status.PENDING
    assert rearmed.manual_review_at is None
    assert rearmed.next_reconciliation_at is not None
    assert rearmed.operation_token is None


def test_audit_scrubber_removes_only_expired_transport_metadata(settings):
    settings.PAYMENT_AUDIT_RETENTION_DAYS = 180
    payment = PaymentFactory(
        initiator_ip="198.51.100.9",
        initiator_user_agent="retained agent",
        first_callback_ip="203.0.113.8",
        callback_count=1,
        first_callback_at=timezone.now(),
        last_callback_at=timezone.now(),
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=181))

    count = scrub_expired_payment_audit_metadata()

    payment.refresh_from_db()
    assert count == 1
    assert payment.initiator_ip is None
    assert payment.first_callback_ip is None
    assert payment.initiator_user_agent == ""
    assert payment.audit_scrubbed_at is not None


def test_audit_scrubber_drains_more_than_one_batch(settings):
    settings.PAYMENT_AUDIT_RETENTION_DAYS = 180
    payments = PaymentFactory.create_batch(101, initiator_ip="198.51.100.9")
    Payment.objects.filter(pk__in=[payment.pk for payment in payments]).update(
        created_at=timezone.now() - timedelta(days=181)
    )

    count = scrub_expired_payment_audit_metadata()

    assert count == 101
    assert not Payment.objects.filter(
        pk__in=[payment.pk for payment in payments],
        audit_scrubbed_at__isnull=True,
    ).exists()


def test_sessionless_payment_enters_manual_review_after_reconciliation_horizon(settings):
    settings.PAYMENT_RECONCILIATION_HORIZON_HOURS = 24
    payment = PaymentFactory(next_reconciliation_at=timezone.now())
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=25))

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.failure_code == "reconciliation_horizon_exceeded"
    assert payment.next_reconciliation_at is None


def test_sessionful_payment_enters_manual_review_after_reconciliation_horizon(settings):
    settings.PAYMENT_RECONCILIATION_HORIZON_HOURS = 24
    payment = PaymentFactory(
        status=Payment.Status.REDIRECT_READY,
        provider_session_id="session-past-horizon",
        redirect_ready_at=timezone.now(),
        next_reconciliation_at=timezone.now(),
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=25))

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.failure_code == "reconciliation_horizon_exceeded"
    assert payment.next_reconciliation_at is None


def test_sessionless_reconciliation_recovers_provider_session(settings):
    register_provider("lookup", LookupProvider())
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    payment = PaymentFactory(provider="lookup", next_reconciliation_at=timezone.now())

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.pending is True
    assert payment.status == Payment.Status.REDIRECT_READY
    assert payment.provider_session_id == "session-recovered"
    assert payment.next_reconciliation_at is not None


def test_sessionless_reconciliation_rejects_malformed_lookup_result():
    register_provider("malformed-lookup", MalformedLookupProvider())
    payment = PaymentFactory(provider="malformed-lookup", next_reconciliation_at=timezone.now())

    result = reconcile_payment(payment_id=payment.pk)

    payment.refresh_from_db()
    assert result.payment.status == Payment.Status.MANUAL_REVIEW
    assert payment.failure_code == "lookup_provider_protocol"
    assert payment.operation_token is None


def test_callback_after_audit_scrub_does_not_recollect_ip_evidence():
    register_provider("reconcile-scrubbed", ReconcileProvider())
    payment = PaymentFactory(
        provider="reconcile-scrubbed",
        status=Payment.Status.REDIRECT_READY,
        provider_session_id="session-scrubbed",
        redirect_ready_at=timezone.now(),
        audit_scrubbed_at=timezone.now(),
        initiator_ip=None,
        first_callback_ip=None,
        initiator_user_agent="",
    )
    payment.order.status = "cancelled"
    payment.order.cancellation_reason = "payment_failed"
    payment.order.cancelled_at = timezone.now()
    payment.order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))

    from apps.payments.services.verification import verify_payment

    verify_payment(
        provider="reconcile-scrubbed",
        provider_session_id="session-scrubbed",
        callback_ip="203.0.113.99",
    )

    payment.refresh_from_db()
    assert payment.first_callback_ip is None
