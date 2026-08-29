from datetime import timedelta
from secrets import randbelow
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.lib.sms.base import (
    SmsConfigurationError,
    SmsProtocolError,
    SmsSendOutcome,
    SmsSendResult,
    SmsTransportError,
)
from apps.lib.sms.registry import ProviderNotRegistered, get_provider
from apps.notifications.audit import emit_notification_event
from apps.notifications.models import SmsDelivery
from apps.notifications.templates import render_message


def _provider_for(delivery):
    try:
        provider = get_provider(delivery.provider)
    except ProviderNotRegistered:
        return None
    if not callable(getattr(provider, "send_sms", None)):
        return None
    return provider


def _retry_delay(attempt):
    cap = int(settings.SMS_RETRY_MAX_SECONDS)
    base = int(settings.SMS_RETRY_BASE_SECONDS)
    delay = min(cap, base * (2 ** max(attempt - 1, 0)))
    return min(cap, delay + (delay * randbelow(21) // 100))


def _schedule_retry_after_commit(delivery, delay):
    def enqueue():
        try:
            from apps.notifications.tasks import execute_sms_delivery_task

            execute_sms_delivery_task.apply_async(args=(delivery.pk,), countdown=delay, retry=False)
        except Exception:
            emit_notification_event("sms_enqueue_failed", delivery=delivery, outcome="broker")

    transaction.on_commit(enqueue)


def _move_to_manual_review(*, delivery_id, token, code):
    with transaction.atomic():
        delivery = SmsDelivery.objects.select_for_update().get(pk=delivery_id)
        if token is not None and delivery.operation_token != token:
            return delivery
        delivery.status = SmsDelivery.Status.MANUAL_REVIEW
        delivery.operation_token = None
        delivery.operation_started_at = None
        delivery.next_retry_at = None
        delivery.manual_review_at = timezone.now()
        delivery.failed_at = None
        delivery.sent_at = None
        delivery.failure_code = code
        delivery.save(update_fields=(
            "status", "operation_token", "operation_started_at", "next_retry_at",
            "manual_review_at", "failed_at", "sent_at", "failure_code", "updated_at",
        ))
    emit_notification_event("sms_manual_review_required", delivery=delivery, outcome=code)
    return delivery


def _claim_delivery(*, delivery_id, provider):
    now = timezone.now()
    with transaction.atomic():
        delivery = SmsDelivery.objects.select_for_update().select_related("order").filter(pk=delivery_id).first()
        if delivery is None or delivery.status in (SmsDelivery.Status.SENT, SmsDelivery.Status.FAILED):
            return None
        if delivery.status == SmsDelivery.Status.MANUAL_REVIEW:
            return None
        if delivery.status == SmsDelivery.Status.SENDING:
            if delivery.next_retry_at and delivery.next_retry_at > now:
                return None
            if provider is None or not getattr(provider, "supports_idempotent_send", False):
                delivery.status = SmsDelivery.Status.MANUAL_REVIEW
                delivery.operation_token = None
                delivery.operation_started_at = None
                delivery.next_retry_at = None
                delivery.manual_review_at = now
                delivery.failure_code = "stale_non_idempotent_lease"
                delivery.save(update_fields=(
                    "status", "operation_token", "operation_started_at", "next_retry_at",
                    "manual_review_at", "failure_code", "updated_at",
                ))
                transaction.on_commit(
                    lambda: emit_notification_event(
                        "sms_manual_review_required", delivery=delivery, outcome="stale_lease"
                    )
                )
                return None
        elif delivery.next_retry_at and delivery.next_retry_at > now:
            return None

        token = uuid4()
        delivery.status = SmsDelivery.Status.SENDING
        delivery.operation_token = token
        delivery.operation_started_at = now
        delivery.last_attempt_at = now
        delivery.next_retry_at = now + timedelta(seconds=settings.SMS_OPERATION_LEASE_SECONDS)
        delivery.attempt_count += 1
        delivery.manual_review_at = None
        delivery.failure_code = ""
        delivery.save(update_fields=(
            "status", "operation_token", "operation_started_at", "last_attempt_at",
            "next_retry_at", "attempt_count", "manual_review_at", "failure_code", "updated_at",
        ))
    emit_notification_event("sms_delivery_started", delivery=delivery, outcome="started")
    return delivery, token


def _schedule_retry(*, delivery_id, token, code):
    with transaction.atomic():
        delivery = SmsDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.operation_token != token:
            return delivery
        if delivery.attempt_count >= settings.SMS_MAX_ATTEMPTS:
            delivery.status = SmsDelivery.Status.MANUAL_REVIEW
            delivery.operation_token = None
            delivery.operation_started_at = None
            delivery.next_retry_at = None
            delivery.manual_review_at = timezone.now()
            delivery.failure_code = "attempts_exhausted"
            delivery.save(update_fields=(
                "status", "operation_token", "operation_started_at", "next_retry_at",
                "manual_review_at", "failure_code", "updated_at",
            ))
            transaction.on_commit(
                lambda: emit_notification_event(
                    "sms_manual_review_required", delivery=delivery, outcome="attempts_exhausted"
                )
            )
            return delivery
        delay = _retry_delay(delivery.attempt_count)
        delivery.status = SmsDelivery.Status.PENDING
        delivery.operation_token = None
        delivery.operation_started_at = None
        delivery.next_retry_at = timezone.now() + timedelta(seconds=delay)
        delivery.failure_code = code
        delivery.save(update_fields=(
            "status", "operation_token", "operation_started_at", "next_retry_at",
            "failure_code", "updated_at",
        ))
        transaction.on_commit(lambda: _schedule_retry_after_commit(delivery, delay))
    emit_notification_event("sms_delivery_retry_scheduled", delivery=delivery, outcome=code)
    return delivery


def _finalize_rejected(*, delivery_id, token, code):
    with transaction.atomic():
        delivery = SmsDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.operation_token != token:
            return delivery
        delivery.status = SmsDelivery.Status.FAILED
        delivery.operation_token = None
        delivery.operation_started_at = None
        delivery.next_retry_at = None
        delivery.failed_at = timezone.now()
        delivery.failure_code = code or "provider_rejected"
        delivery.save(update_fields=(
            "status", "operation_token", "operation_started_at", "next_retry_at",
            "failed_at", "failure_code", "updated_at",
        ))
    emit_notification_event("sms_delivery_failed", delivery=delivery, outcome=delivery.failure_code)
    return delivery


def _finalize_accepted(*, delivery_id, token, result):
    try:
        with transaction.atomic():
            delivery = SmsDelivery.objects.select_for_update().get(pk=delivery_id)
            if delivery.operation_token != token:
                return delivery
            delivery.status = SmsDelivery.Status.SENT
            delivery.operation_token = None
            delivery.operation_started_at = None
            delivery.next_retry_at = None
            delivery.sent_at = timezone.now()
            delivery.provider_message_id = result.provider_message_id
            delivery.failure_code = ""
            delivery.save(update_fields=(
                "status", "operation_token", "operation_started_at", "next_retry_at",
                "sent_at", "provider_message_id", "failure_code", "updated_at",
            ))
    except IntegrityError:
        return _move_to_manual_review(
            delivery_id=delivery_id,
            token=token,
            code="provider_message_conflict",
        )
    emit_notification_event("sms_delivery_succeeded", delivery=delivery, outcome="accepted")
    return delivery


def execute_delivery(*, delivery_id):
    """Claim one outbox obligation and call the provider outside database locks."""
    if not getattr(settings, "SMS_ENABLED", False):
        return None
    delivery = SmsDelivery.objects.filter(pk=delivery_id).select_related("order").first()
    if delivery is None:
        return None
    provider = _provider_for(delivery)
    claim = _claim_delivery(delivery_id=delivery_id, provider=provider)
    if claim is None:
        return None
    delivery, token = claim
    if provider is None:
        return _move_to_manual_review(delivery_id=delivery.pk, token=token, code="provider_configuration")
    try:
        result = provider.send_sms(
            client_reference=delivery.uuid,
            recipient=delivery.recipient_phone,
            message=render_message(delivery.event_type, delivery.order.uuid),
        )
    except SmsTransportError:
        return _schedule_retry(delivery_id=delivery.pk, token=token, code="transport_error")
    except SmsConfigurationError:
        return _move_to_manual_review(delivery_id=delivery.pk, token=token, code="provider_configuration")
    except SmsProtocolError:
        return _move_to_manual_review(delivery_id=delivery.pk, token=token, code="provider_protocol")
    except Exception:
        return _move_to_manual_review(delivery_id=delivery.pk, token=token, code="provider_unexpected")
    if not isinstance(result, SmsSendResult):
        return _move_to_manual_review(delivery_id=delivery.pk, token=token, code="provider_protocol")
    if result.outcome == SmsSendOutcome.ACCEPTED:
        return _finalize_accepted(delivery_id=delivery.pk, token=token, result=result)
    if result.outcome == SmsSendOutcome.REJECTED:
        return _finalize_rejected(
            delivery_id=delivery.pk,
            token=token,
            code=result.diagnostic_code or "provider_rejected",
        )
    if result.outcome == SmsSendOutcome.AMBIGUOUS and getattr(provider, "supports_idempotent_send", False):
        return _schedule_retry(delivery_id=delivery.pk, token=token, code="ambiguous")
    return _move_to_manual_review(
        delivery_id=delivery.pk,
        token=token,
        code="ambiguous_non_idempotent",
    )


def rearm_manual_delivery(*, delivery_id):
    with transaction.atomic():
        delivery = SmsDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status != SmsDelivery.Status.MANUAL_REVIEW:
            raise ValueError("Only manual-review SMS deliveries can be re-armed.")
        if not delivery.recipient_phone:
            raise ValueError("A scrubbed or invalid recipient cannot be re-armed.")
        delivery.status = SmsDelivery.Status.PENDING
        delivery.manual_review_at = None
        delivery.failure_code = ""
        delivery.next_retry_at = timezone.now()
        delivery.save(update_fields=("status", "manual_review_at", "failure_code", "next_retry_at", "updated_at"))
        transaction.on_commit(lambda: _schedule_retry_after_commit(delivery, 0))
    return delivery
