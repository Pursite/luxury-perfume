from datetime import timedelta
from uuid import uuid4

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.payments.audit import emit_payment_event
from apps.payments.exceptions import (
    ProviderProtocolError,
    ProviderSecurityError,
    ProviderTransportError,
    RefundNotEligibleError,
)
from apps.payments.models import Payment, Refund
from apps.payments.providers.base import RefundOutcome, RefundResult, is_valid_provider_identifier
from apps.payments.providers.registry import ProviderNotRegistered, get_provider


REFUND_LEASE_SECONDS = 30


def create_refund_obligation(*, payment, reason):
    if payment.status != Payment.Status.VERIFIED or payment.captured_amount is None:
        raise RefundNotEligibleError("Only a verified capture can be refunded.")
    refund, _created = Refund.objects.get_or_create(
        payment=payment,
        defaults={
            "provider": payment.provider,
            "reason": reason,
            "amount": payment.captured_amount,
            "currency": payment.captured_currency,
            "next_retry_at": timezone.now(),
        },
    )
    from apps.payments.tasks import execute_refund_task

    transaction.on_commit(lambda: execute_refund_task.delay(refund.pk))
    if _created:
        emit_payment_event("refund_queued", payment=payment, refund=refund, outcome=reason)
    return refund


def execute_refund(*, refund_id):
    now = timezone.now()
    token = uuid4()
    with transaction.atomic():
        payment_id = Refund.objects.only("payment_id").get(pk=refund_id).payment_id
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status == Refund.Status.REFUNDED:
            return refund
        if (
            refund.status == Refund.Status.PROCESSING
            and refund.operation_token
            and refund.operation_started_at
            and refund.operation_started_at > now - timedelta(seconds=REFUND_LEASE_SECONDS)
        ):
            return refund
        if refund.amount != payment.captured_amount or refund.currency != payment.captured_currency:
            raise RefundNotEligibleError("Refund no longer matches the captured payment.")
        refund.status = Refund.Status.PROCESSING
        refund.operation_token = token
        refund.operation_started_at = now
        refund.processing_at = refund.processing_at or now
        refund.attempt_count += 1
        refund.save(update_fields=("status", "operation_token", "operation_started_at", "processing_at", "attempt_count", "updated_at"))

    try:
        adapter = get_provider(refund.provider)
        result = adapter.refund_payment(
            refund_uuid=refund.uuid,
            provider_transaction_id=payment.provider_transaction_id,
            amount=refund.amount,
            currency=refund.currency,
        )
    except ProviderNotRegistered:
        result = RefundResult(outcome=RefundOutcome.REJECTED, diagnostic_code="refund_provider_unavailable")
    except ProviderTransportError:
        result = RefundResult(outcome=RefundOutcome.AMBIGUOUS, diagnostic_code="transport_error")
    except (ProviderProtocolError, ProviderSecurityError):
        result = RefundResult(outcome=RefundOutcome.REJECTED, diagnostic_code="refund_provider_protocol")
    if (
        not isinstance(result, RefundResult)
        or not isinstance(result.outcome, RefundOutcome)
        or not is_valid_provider_identifier(result.provider_refund_id, required=False)
        or not is_valid_provider_identifier(result.provider_receipt_id, required=False)
    ):
        result = RefundResult(outcome=RefundOutcome.REJECTED, diagnostic_code="refund_provider_protocol")

    with transaction.atomic():
        Payment.objects.select_for_update().get(pk=payment.pk)
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        if refund.operation_token != token or refund.status == Refund.Status.REFUNDED:
            return refund
        if result.outcome in (RefundOutcome.REFUNDED, RefundOutcome.ALREADY_REFUNDED) and result.provider_refund_id:
            refund.status = Refund.Status.REFUNDED
            refund.provider_refund_id = result.provider_refund_id
            refund.provider_receipt_id = result.provider_receipt_id
            refund.refunded_at = timezone.now()
            refund.operation_token = None
            refund.operation_started_at = None
            refund.next_retry_at = None
            refund.failure_code = ""
            refund.failure_message = ""
            try:
                with transaction.atomic():
                    refund.save(update_fields=("status", "provider_refund_id", "provider_receipt_id", "refunded_at", "operation_token", "operation_started_at", "next_retry_at", "failure_code", "failure_message", "updated_at"))
            except IntegrityError:
                _set_manual_review(refund, "refund_identity_conflict")
        elif result.outcome == RefundOutcome.REJECTED:
            _set_manual_review(refund, result.diagnostic_code or "refund_rejected")
        elif refund.attempt_count >= 5:
            _set_manual_review(refund, result.diagnostic_code or "refund_attempts_exhausted")
        else:
            refund.status = Refund.Status.PENDING
            refund.operation_token = None
            refund.operation_started_at = None
            refund.last_failed_at = timezone.now()
            delay_seconds = min(5 * (2 ** (refund.attempt_count - 1)), 300)
            refund.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
            refund.failure_code = (result.diagnostic_code or "refund_ambiguous")[:64]
            refund.save(update_fields=("status", "operation_token", "operation_started_at", "last_failed_at", "next_retry_at", "failure_code", "updated_at"))
        resolved = refund
    _emit_refund_events(resolved)
    return resolved


def _set_manual_review(refund, code):
    refund.status = Refund.Status.MANUAL_REVIEW
    refund.manual_review_at = timezone.now()
    refund.failure_code = code[:64]
    refund.operation_token = None
    refund.operation_started_at = None
    refund.save(update_fields=("status", "manual_review_at", "failure_code", "operation_token", "operation_started_at", "updated_at"))


def _emit_refund_events(refund):
    if refund.status == Refund.Status.REFUNDED:
        emit_payment_event("refund_succeeded", refund=refund, outcome="refunded")
    elif refund.status == Refund.Status.MANUAL_REVIEW:
        emit_payment_event("refund_manual_review_required", refund=refund, outcome="manual_review")
    elif refund.status == Refund.Status.PENDING:
        emit_payment_event("refund_retry_scheduled", refund=refund, outcome="retry_scheduled")


def record_manual_refund_completion(
    *, refund_id, completed_by, provider_refund_id, confirmed=False,
):
    if not confirmed or not getattr(completed_by, "is_active", False) or not getattr(completed_by, "is_superuser", False):
        raise RefundNotEligibleError("Manual refund completion requires explicit superuser confirmation.")
    if not is_valid_provider_identifier(provider_refund_id):
        raise RefundNotEligibleError("A valid external refund reference is required.")

    completed_refund = None
    with transaction.atomic():
        payment_id = Refund.objects.only("payment_id").get(pk=refund_id).payment_id
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status == Refund.Status.REFUNDED:
            if refund.provider_refund_id == provider_refund_id:
                return refund
            raise RefundNotEligibleError("The refund is already completed with different evidence.")
        if refund.status != Refund.Status.MANUAL_REVIEW:
            raise RefundNotEligibleError("Only a manual-review refund can be completed externally.")
        if refund.amount != payment.captured_amount or refund.currency != payment.captured_currency:
            raise RefundNotEligibleError("Refund no longer matches the captured payment.")

        refund.status = Refund.Status.REFUNDED
        refund.provider_refund_id = provider_refund_id
        refund.refunded_at = timezone.now()
        refund.completed_by = completed_by
        refund.operation_token = None
        refund.operation_started_at = None
        refund.next_retry_at = None
        refund.failure_code = ""
        refund.failure_message = ""
        try:
            with transaction.atomic():
                refund.save(update_fields=(
                    "status", "provider_refund_id", "refunded_at", "completed_by",
                    "operation_token", "operation_started_at", "next_retry_at",
                    "failure_code", "failure_message", "updated_at",
                ))
        except IntegrityError as exc:
            raise RefundNotEligibleError("The external refund reference is already in use.") from exc

        LogEntry.objects.create(
            user=completed_by,
            content_type=ContentType.objects.get_for_model(Refund),
            object_id=str(refund.pk),
            object_repr=str(refund),
            action_flag=CHANGE,
            change_message="Recorded confirmed external refund completion.",
        )
        completed_refund = refund
    emit_payment_event("refund_succeeded", refund=completed_refund, outcome="manual_refunded")
    return completed_refund
