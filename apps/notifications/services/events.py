from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.lib.sms.phone import normalize_iranian_mobile
from apps.notifications.audit import emit_notification_event
from apps.notifications.models import SmsDelivery


def _enqueue_after_commit(delivery):
    def enqueue():
        try:
            from apps.notifications.tasks import execute_sms_delivery_task

            execute_sms_delivery_task.apply_async(args=(delivery.pk,), retry=False)
        except Exception:  # Broker publication must not affect the committed order.
            emit_notification_event("sms_enqueue_failed", delivery=delivery, outcome="broker")

    transaction.on_commit(enqueue)


def _create_delivery(*, order, event_type, recipient_type, recipient_phone):
    phone = normalize_iranian_mobile(recipient_phone)
    now = timezone.now()
    values = {
        "order": order,
        "event_type": event_type,
        "recipient_type": recipient_type,
        "recipient_phone": phone,
        "provider": getattr(settings, "SMS_PROVIDER", ""),
    }
    if phone is None:
        values.update(
            status=SmsDelivery.Status.FAILED,
            failed_at=now,
            failure_code="invalid_recipient",
        )
    else:
        values.update(status=SmsDelivery.Status.PENDING, next_retry_at=now)
    try:
        delivery = SmsDelivery.objects.create(**values)
    except IntegrityError:
        return SmsDelivery.objects.get(order=order, event_type=event_type)
    emit_notification_event("notification_created", delivery=delivery, order=order)
    if delivery.status == SmsDelivery.Status.PENDING:
        _enqueue_after_commit(delivery)
    return delivery


def create_processing_sms_deliveries(*, order):
    if not getattr(settings, "SMS_ENABLED", False):
        return ()
    return (
        _create_delivery(
            order=order,
            event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
            recipient_type=SmsDelivery.RecipientType.CUSTOMER,
            recipient_phone=order.customer_phone_number,
        ),
        _create_delivery(
            order=order,
            event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
            recipient_type=SmsDelivery.RecipientType.OWNER,
            recipient_phone=getattr(settings, "ORDER_PROCESSING_ALERT_PHONE", ""),
        ),
    )


def create_shipped_sms_delivery(*, order):
    if not getattr(settings, "SMS_ENABLED", False):
        return None
    return _create_delivery(
        order=order,
        event_type=SmsDelivery.EventType.CUSTOMER_ORDER_SHIPPED,
        recipient_type=SmsDelivery.RecipientType.CUSTOMER,
        recipient_phone=order.customer_phone_number,
    )
