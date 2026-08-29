from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.lib.tasks import CorrelatedTask
from apps.notifications.audit import emit_notification_event
from apps.notifications.models import SmsDelivery


TASK_OPTIONS = {"base": CorrelatedTask, "soft_time_limit": 25, "time_limit": 30}
SWEEP_BATCH_SIZE = 100
SCRUB_MAX_BATCHES = 100


@shared_task(**TASK_OPTIONS)
def execute_sms_delivery_task(delivery_id):
    from apps.notifications.services.delivery import execute_delivery

    return execute_delivery(delivery_id=delivery_id)


@shared_task(**TASK_OPTIONS)
def sweep_due_sms_deliveries():
    if not getattr(settings, "SMS_ENABLED", False):
        return 0
    now = timezone.now()
    with transaction.atomic():
        candidate_ids = list(
            SmsDelivery.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status=SmsDelivery.Status.PENDING, next_retry_at__lte=now)
                | Q(status=SmsDelivery.Status.SENDING, next_retry_at__lte=now)
            )
            .order_by("next_retry_at", "id")
            .values_list("id", flat=True)[:SWEEP_BATCH_SIZE]
        )
    for delivery_id in candidate_ids:
        try:
            execute_sms_delivery_task.apply_async(args=(delivery_id,), retry=False)
        except Exception:
            # The durable row remains due for the next sweep.
            emit_notification_event("sms_enqueue_failed", outcome="broker")
    return len(candidate_ids)


@shared_task(**TASK_OPTIONS)
def scrub_expired_sms_recipients():
    if not getattr(settings, "SMS_ENABLED", False):
        return 0
    cutoff = timezone.now() - timedelta(days=settings.SMS_RECIPIENT_RETENTION_DAYS)
    scrubbed_at = timezone.now()
    scrubbed = 0
    for _batch in range(SCRUB_MAX_BATCHES):
        candidate_ids = list(
            SmsDelivery.objects.filter(
                status__in=(SmsDelivery.Status.SENT, SmsDelivery.Status.FAILED),
                recipient_phone__isnull=False,
                audit_scrubbed_at__isnull=True,
                created_at__lt=cutoff,
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:SWEEP_BATCH_SIZE]
        )
        if not candidate_ids:
            break
        scrubbed += SmsDelivery.objects.filter(pk__in=candidate_ids).update(
            recipient_phone=None,
            audit_scrubbed_at=scrubbed_at,
        )
        if len(candidate_ids) < SWEEP_BATCH_SIZE:
            break
    return scrubbed
