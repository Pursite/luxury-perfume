from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.transitions import expire_unpaid_order
from apps.payments.exceptions import (
    PaymentNotFoundError,
    PaymentProviderProtocolError,
    ProviderProtocolError,
    ProviderSecurityError,
    ProviderTransportError,
)
from apps.payments.models import Payment
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    is_valid_provider_identifier,
    validate_redirect_url,
)
from apps.payments.providers.registry import ProviderNotRegistered, get_provider
from apps.payments.services.verification import PaymentVerificationServiceResult, verify_payment


def reconcile_payment(*, payment_id):
    token = uuid4()
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
        if payment is None:
            raise PaymentNotFoundError("Payment not found.")
        if payment.status == Payment.Status.VERIFIED:
            return PaymentVerificationServiceResult(payment=payment, refund=payment.refunds.first())
        provider_session_id = payment.provider_session_id
        provider = payment.provider
        now = timezone.now()
        if payment.operation_token and payment.operation_started_at and payment.operation_started_at > now - timedelta(seconds=30):
            return PaymentVerificationServiceResult(payment=payment, pending=True)
        horizon = payment.created_at + timedelta(hours=settings.PAYMENT_RECONCILIATION_HORIZON_HOURS)
        if now >= horizon and payment.status != Payment.Status.MANUAL_REVIEW:
            payment.status = Payment.Status.MANUAL_REVIEW
            payment.manual_review_at = now
            payment.failure_code = "reconciliation_horizon_exceeded"
            payment.next_reconciliation_at = None
            payment.operation_token = None
            payment.operation_started_at = None
            payment.save(update_fields=(
                "status", "manual_review_at", "failure_code",
                "next_reconciliation_at", "operation_token",
                "operation_started_at", "updated_at",
            ))
            return PaymentVerificationServiceResult(payment=payment)
        if not provider_session_id:
            payment.reconciliation_attempts += 1
            payment.last_reconciled_at = now
            payment.operation_token = token
            payment.operation_started_at = now
            payment.save(update_fields=("reconciliation_attempts", "last_reconciled_at", "operation_token", "operation_started_at", "updated_at"))
    if provider_session_id:
        return verify_payment(
            provider=provider,
            provider_session_id=provider_session_id,
            record_callback=False,
        )
    try:
        adapter = get_provider(provider)
        result = adapter.lookup_payment(
            payment_uuid=payment.uuid,
            expected_amount=payment.amount,
            expected_currency=payment.currency,
        )
    except ProviderTransportError:
        result = PaymentInitiationResult(outcome=InitiationOutcome.AMBIGUOUS, diagnostic_code="lookup_transport")
    except (ProviderNotRegistered, ProviderProtocolError, ProviderSecurityError):
        return _finish_sessionless_lookup(payment_id=payment.pk, token=token, result=None)
    if not isinstance(result, PaymentInitiationResult) or not isinstance(result.outcome, InitiationOutcome):
        result = None
    return _finish_sessionless_lookup(payment_id=payment.pk, token=token, result=result)


def _finish_sessionless_lookup(*, payment_id, token, result):
    order_id = Payment.objects.only("order_id").get(pk=payment_id).order_id
    expired_order_id = None
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.operation_token != token:
            return PaymentVerificationServiceResult(payment=payment, pending=True)
        payment.operation_token = None
        payment.operation_started_at = None
        if result is None:
            payment.status = Payment.Status.MANUAL_REVIEW
            payment.manual_review_at = timezone.now()
            payment.failure_code = "lookup_provider_protocol"
            payment.next_reconciliation_at = None
            payment.save(update_fields=("status", "manual_review_at", "failure_code", "next_reconciliation_at", "operation_token", "operation_started_at", "updated_at"))
            return PaymentVerificationServiceResult(payment=payment)
        if result.outcome == InitiationOutcome.READY:
            try:
                if not is_valid_provider_identifier(result.provider_session_id) or not result.redirect_url:
                    raise PaymentProviderProtocolError("Incomplete lookup result.")
                validate_redirect_url(result.redirect_url, allowed_hosts=settings.PAYMENT_ALLOWED_REDIRECT_HOSTS)
                payment.provider_session_id = result.provider_session_id
                payment.redirect_ready_at = timezone.now()
                payment.status = Payment.Status.REDIRECT_READY
                payment.next_reconciliation_at = timezone.now() + timedelta(minutes=1)
                with transaction.atomic():
                    payment.save(update_fields=("provider_session_id", "redirect_ready_at", "status", "next_reconciliation_at", "operation_token", "operation_started_at", "updated_at"))
            except (IntegrityError, PaymentProviderProtocolError):
                payment.provider_session_id = None
                payment.redirect_ready_at = None
                payment.status = Payment.Status.MANUAL_REVIEW
                payment.manual_review_at = timezone.now()
                payment.failure_code = "lookup_identity_conflict"
                payment.next_reconciliation_at = None
                payment.save(update_fields=("provider_session_id", "redirect_ready_at", "status", "manual_review_at", "failure_code", "next_reconciliation_at", "operation_token", "operation_started_at", "updated_at"))
                return PaymentVerificationServiceResult(payment=payment)
            if order.status != Order.Status.WAITING_FOR_PAYMENT or timezone.now() >= order.reservation_expires_at:
                expired_order_id = order.pk
        elif result.outcome == InitiationOutcome.REJECTED:
            payment.status = Payment.Status.FAILED
            payment.failed_at = timezone.now()
            payment.failure_code = (result.diagnostic_code or "lookup_rejected")[:64]
            payment.next_reconciliation_at = None
            payment.save(update_fields=("status", "failed_at", "failure_code", "next_reconciliation_at", "operation_token", "operation_started_at", "updated_at"))
        else:
            cadence_minutes = (1, 2, 5, 10, 30)
            index = min(payment.reconciliation_attempts - 1, len(cadence_minutes))
            delay = cadence_minutes[index] if index < len(cadence_minutes) else 60
            payment.next_reconciliation_at = timezone.now() + timedelta(minutes=delay)
            payment.failure_code = (result.diagnostic_code or "lookup_ambiguous")[:64]
            payment.save(update_fields=("next_reconciliation_at", "failure_code", "operation_token", "operation_started_at", "updated_at"))
    if expired_order_id is not None:
        expire_unpaid_order(order_id=expired_order_id)
    return PaymentVerificationServiceResult(payment=payment, pending=True)
