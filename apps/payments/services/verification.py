from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.transitions import TransitionOutcome, cancel_failed_payment, confirm_verified_payment
from apps.payments.audit import emit_payment_event
from apps.payments.exceptions import (
    PaymentNotFoundError,
    ProviderProtocolError,
    ProviderSecurityError,
    ProviderTransportError,
)
from apps.payments.models import Payment, Refund
from apps.payments.providers.base import (
    PaymentVerificationResult,
    VerificationOutcome,
    is_valid_provider_identifier,
)
from apps.payments.providers.registry import ProviderNotRegistered, get_provider
from apps.payments.services.refunds import create_refund_obligation


VERIFY_LEASE_SECONDS = 30


@dataclass(frozen=True)
class PaymentVerificationServiceResult:
    payment: Payment
    refund: Refund | None = None
    pending: bool = False


def verify_payment(*, provider, provider_session_id, callback_ip=None, record_callback=True):
    try:
        adapter = get_provider(provider)
    except ProviderNotRegistered as exc:
        raise PaymentNotFoundError("Payment not found.") from exc
    now = timezone.now()
    token = uuid4()
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            provider=provider,
            provider_session_id=provider_session_id,
        ).first()
        if payment is None:
            raise PaymentNotFoundError("Payment not found.")
        callback_fields = []
        if record_callback:
            payment.callback_count += 1
            payment.first_callback_at = payment.first_callback_at or now
            payment.last_callback_at = now
            if payment.audit_scrubbed_at is None:
                payment.first_callback_ip = payment.first_callback_ip or callback_ip
            callback_fields = ["callback_count", "first_callback_at", "last_callback_at", "first_callback_ip", "updated_at"]
        if payment.status == Payment.Status.VERIFIED:
            if callback_fields:
                payment.save(update_fields=callback_fields)
            return PaymentVerificationServiceResult(payment=payment, refund=payment.refunds.first())
        if payment.operation_token and payment.operation_started_at and payment.operation_started_at > now - timedelta(seconds=VERIFY_LEASE_SECONDS):
            payment.save(update_fields=callback_fields)
            return PaymentVerificationServiceResult(payment=payment, pending=True)
        # A prior initiation can have been definitively marked failed, allowing
        # a newer open attempt on the same Order.  A later provider callback for
        # that old authority still needs authoritative server verification, but
        # must not become a second ``VERIFYING`` row and violate the one-open-
        # attempt invariant.  Keep its terminal status until finalization.
        retain_failed_status = payment.status == Payment.Status.FAILED
        reconciliation_fields = []
        if not record_callback:
            payment.reconciliation_attempts += 1
            payment.last_reconciled_at = now
            reconciliation_fields = ["reconciliation_attempts", "last_reconciled_at"]
        payment.operation_token = token
        payment.operation_started_at = now
        state_fields = ["operation_token", "operation_started_at"]
        if not retain_failed_status:
            payment.status = Payment.Status.VERIFYING
            payment.failed_at = None
            payment.manual_review_at = None
            payment.failure_code = ""
            state_fields += ["status", "failed_at", "manual_review_at", "failure_code"]
        payment.save(update_fields=callback_fields + reconciliation_fields + state_fields)

    if record_callback:
        emit_payment_event(
            "payment_callback_received",
            payment=payment,
            provider=provider,
            outcome="received",
        )

    try:
        result = adapter.verify_payment(
            provider_session_id=provider_session_id,
            expected_amount=payment.amount,
            expected_currency=payment.currency,
        )
    except ProviderTransportError:
        emit_payment_event("payment_provider_error", payment=payment, provider=provider, outcome="transport")
        result = PaymentVerificationResult(outcome=VerificationOutcome.AMBIGUOUS, diagnostic_code="transport_error")
    except ProviderProtocolError:
        resolved = _return_to_reconciliation(payment_id=payment.pk, token=token, code="verification_protocol")
        emit_payment_event("payment_provider_error", payment=resolved.payment, provider=provider, outcome="protocol")
        return _emit_verification_events(resolved)
    except ProviderSecurityError:
        resolved = _move_to_manual_review(payment_id=payment.pk, token=token, code="provider_security")
        emit_payment_event("payment_provider_error", payment=resolved.payment, provider=provider, outcome="security")
        return _emit_verification_events(resolved)
    if not isinstance(result, PaymentVerificationResult) or not isinstance(result.outcome, VerificationOutcome):
        resolved = _return_to_reconciliation(payment_id=payment.pk, token=token, code="verification_protocol")
        emit_payment_event("payment_provider_error", payment=resolved.payment, provider=provider, outcome="protocol")
        return _emit_verification_events(resolved)
    if result.outcome == VerificationOutcome.VERIFIED:
        try:
            _validate_capture_result(result)
        except (InvalidOperation, TypeError, ValidationError, ValueError):
            resolved = _return_to_reconciliation(payment_id=payment.pk, token=token, code="verification_protocol")
            emit_payment_event("payment_provider_error", payment=resolved.payment, provider=provider, outcome="protocol")
            return _emit_verification_events(resolved)
    try:
        resolved = _finalize_verification(payment_id=payment.pk, token=token, result=result)
    except IntegrityError:
        resolved = _move_to_manual_review(payment_id=payment.pk, token=token, code="financial_identity_conflict")
        emit_payment_event("payment_provider_error", payment=resolved.payment, provider=provider, outcome="identity_conflict")
    return _emit_verification_events(resolved)


def _emit_verification_events(resolved):
    payment = resolved.payment
    if payment.status == Payment.Status.VERIFIED:
        emit_payment_event("payment_verification_succeeded", payment=payment, outcome="verified")
        if resolved.refund and resolved.refund.reason == Refund.Reason.LATE_PAYMENT:
            emit_payment_event("payment_late", payment=payment, refund=resolved.refund, outcome="late")
    elif payment.status == Payment.Status.FAILED:
        emit_payment_event("payment_verification_failed", payment=payment, outcome="failed")
    elif payment.status == Payment.Status.MANUAL_REVIEW:
        emit_payment_event("payment_manual_review_required", payment=payment, outcome="manual_review")
    return resolved


def _return_to_reconciliation(*, payment_id, token, code):
    with transaction.atomic():
        _order, payment, stale_terminal_authority, _other_applied = _lock_resolution_context(payment_id)
        if payment.operation_token != token:
            return PaymentVerificationServiceResult(payment=payment, pending=True)
        if stale_terminal_authority:
            _preserve_stale_failed_payment(payment, code)
            return PaymentVerificationServiceResult(payment=payment)
        payment.status = Payment.Status.REDIRECT_READY
        payment.operation_token = None
        payment.operation_started_at = None
        payment.next_reconciliation_at = timezone.now() + timedelta(minutes=1)
        payment.failure_code = code
        payment.save(update_fields=("status", "operation_token", "operation_started_at", "next_reconciliation_at", "failure_code", "updated_at"))
        return PaymentVerificationServiceResult(payment=payment, pending=True)


def _move_to_manual_review(*, payment_id, token, code):
    with transaction.atomic():
        _order, payment, stale_terminal_authority, _other_applied = _lock_resolution_context(payment_id)
        if payment.operation_token != token:
            return PaymentVerificationServiceResult(payment=payment, refund=payment.refunds.first())
        if stale_terminal_authority:
            _preserve_stale_failed_payment(payment, code)
            return PaymentVerificationServiceResult(payment=payment)
        payment.status = Payment.Status.MANUAL_REVIEW
        payment.manual_review_at = timezone.now()
        payment.failure_code = code
        payment.next_reconciliation_at = None
        payment.operation_token = None
        payment.operation_started_at = None
        payment.save(update_fields=(
            "status", "manual_review_at", "failure_code",
            "next_reconciliation_at", "operation_token",
            "operation_started_at", "updated_at",
        ))
        return PaymentVerificationServiceResult(payment=payment)


def _finalize_verification(*, payment_id, token, result):
    with transaction.atomic():
        order, payment, stale_terminal_authority, other_applied = _lock_resolution_context(payment_id)
        if result.outcome != VerificationOutcome.VERIFIED and payment.operation_token != token:
            return PaymentVerificationServiceResult(payment=payment, refund=payment.refunds.first(), pending=True)
        if result.outcome == VerificationOutcome.AMBIGUOUS:
            if stale_terminal_authority:
                _preserve_stale_failed_payment(payment, result.diagnostic_code or "verification_ambiguous")
                return PaymentVerificationServiceResult(payment=payment)
            payment.status = Payment.Status.REDIRECT_READY
            payment.operation_token = None
            payment.operation_started_at = None
            payment.next_reconciliation_at = timezone.now() + timedelta(minutes=1)
            payment.failure_code = (result.diagnostic_code or "verification_ambiguous")[:64]
            payment.save(update_fields=("status", "operation_token", "operation_started_at", "next_reconciliation_at", "failure_code", "updated_at"))
            return PaymentVerificationServiceResult(payment=payment, pending=True)
        if result.outcome == VerificationOutcome.NOT_PAID:
            payment.status = Payment.Status.FAILED
            payment.failed_at = timezone.now()
            payment.failure_code = (result.diagnostic_code or "not_paid")[:64]
            payment.operation_token = None
            payment.operation_started_at = None
            payment.captured_amount = None
            payment.captured_currency = None
            payment.verified_at = None
            payment.save(update_fields=("status", "failed_at", "failure_code", "operation_token", "operation_started_at", "captured_amount", "captured_currency", "verified_at", "updated_at"))
            if not stale_terminal_authority and order.status == Order.Status.WAITING_FOR_PAYMENT:
                cancel_failed_payment(order_id=order.pk)
            return PaymentVerificationServiceResult(payment=payment)

        _validate_capture_result(result)
        payment.status = Payment.Status.VERIFIED
        payment.provider_transaction_id = result.provider_transaction_id
        payment.provider_receipt_id = result.provider_receipt_id
        payment.captured_amount = Decimal(result.captured_amount)
        payment.captured_currency = result.captured_currency
        payment.provider_paid_at = result.provider_paid_at
        payment.verified_at = timezone.now()
        payment.failed_at = None
        payment.manual_review_at = None
        payment.failure_code = ""
        payment.failure_message = ""
        payment.operation_token = None
        payment.operation_started_at = None
        payment.next_reconciliation_at = None
        payment.save(update_fields=(
            "status", "provider_transaction_id", "provider_receipt_id", "captured_amount",
            "captured_currency", "provider_paid_at", "verified_at", "failed_at",
            "manual_review_at", "failure_code", "failure_message", "operation_token",
            "operation_started_at", "next_reconciliation_at", "updated_at",
        ))

        mismatch = payment.captured_amount != payment.amount or payment.captured_currency != payment.currency
        refund = None
        if mismatch:
            if not stale_terminal_authority and order.status == Order.Status.WAITING_FOR_PAYMENT:
                cancel_failed_payment(order_id=order.pk)
            refund = create_refund_obligation(payment=payment, reason=Refund.Reason.AMOUNT_MISMATCH)
        elif other_applied:
            refund = create_refund_obligation(payment=payment, reason=Refund.Reason.DUPLICATE_PAYMENT)
        else:
            transition = confirm_verified_payment(order_id=order.pk)
            if transition.outcome == TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED:
                refund = create_refund_obligation(payment=payment, reason=Refund.Reason.LATE_PAYMENT)
            else:
                payment.applied_to_order_at = payment.applied_to_order_at or timezone.now()
                payment.save(update_fields=("applied_to_order_at", "updated_at"))
        return PaymentVerificationServiceResult(payment=payment, refund=refund)


def _lock_resolution_context(payment_id):
    """Lock the Order, then the callback Payment and any current open attempt."""
    order_id = Payment.objects.only("order_id").get(pk=payment_id).order_id
    order = Order.objects.select_for_update().get(pk=order_id)
    payments = list(
        Payment.objects.select_for_update()
        .filter(order=order)
        .filter(
            Q(pk=payment_id)
            | Q(status__in=Payment.OPEN_STATUSES)
            | Q(applied_to_order_at__isnull=False)
        )
        .order_by("pk")
    )
    payment = next(item for item in payments if item.pk == payment_id)
    has_current_open_attempt = any(
        item.pk != payment.pk and item.status in Payment.OPEN_STATUSES
        for item in payments
    )
    has_other_applied = any(item.pk != payment.pk and item.applied_to_order_at is not None for item in payments)
    return (
        order,
        payment,
        payment.status == Payment.Status.FAILED and has_current_open_attempt,
        has_other_applied,
    )


def _preserve_stale_failed_payment(payment, code):
    """Release a stale callback claim without granting it current order authority."""
    payment.operation_token = None
    payment.operation_started_at = None
    payment.next_reconciliation_at = None
    payment.failure_code = code[:64]
    payment.save(update_fields=(
        "operation_token", "operation_started_at", "next_reconciliation_at",
        "failure_code", "updated_at",
    ))


def _validate_capture_result(result):
    captured_amount = Decimal(result.captured_amount)
    DecimalValidator(max_digits=24, decimal_places=2)(captured_amount)
    if (
        not is_valid_provider_identifier(result.provider_transaction_id)
        or not is_valid_provider_identifier(result.provider_receipt_id, required=False)
        or result.captured_amount is None
        or not captured_amount.is_finite()
        or captured_amount <= 0
        or not isinstance(result.captured_currency, str)
        or len(result.captured_currency) != 3
        or not result.captured_currency.isascii()
        or not result.captured_currency.isupper()
        or (
            result.provider_paid_at is not None
            and (
                not isinstance(result.provider_paid_at, datetime)
                or timezone.is_naive(result.provider_paid_at)
            )
        )
    ):
        raise ValueError("Provider verification did not contain a complete capture identity.")
