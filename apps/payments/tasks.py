from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.lib.tasks import CorrelatedTask


TASK_OPTIONS = {"base": CorrelatedTask, "soft_time_limit": 25, "time_limit": 30}
SWEEP_BATCH_SIZE = 100
SCRUB_MAX_BATCHES = 100


@shared_task(**TASK_OPTIONS)
def execute_refund_task(refund_id):
    from apps.payments.services.refunds import execute_refund

    execute_refund(refund_id=refund_id)


@shared_task(**TASK_OPTIONS)
def reconcile_payment_task(payment_id):
    from apps.payments.services.reconciliation import reconcile_payment

    reconcile_payment(payment_id=payment_id)


@shared_task(**TASK_OPTIONS)
def sweep_reconcilable_payments():
    from apps.payments.models import Payment

    candidate_ids = list(
        Payment.objects.filter(
            status__in=Payment.RECONCILABLE_STATUSES,
            next_reconciliation_at__lte=timezone.now(),
        )
        .order_by("next_reconciliation_at", "id")
        .values_list("id", flat=True)[:SWEEP_BATCH_SIZE]
    )
    for payment_id in candidate_ids:
        reconcile_payment_task.delay(payment_id)
    return len(candidate_ids)


@shared_task(**TASK_OPTIONS)
def sweep_pending_refunds():
    from apps.payments.models import Refund

    candidate_ids = list(
        Refund.objects.filter(
            status__in=(Refund.Status.PENDING, Refund.Status.PROCESSING),
            next_retry_at__lte=timezone.now(),
        )
        .order_by("next_retry_at", "id")
        .values_list("id", flat=True)[:SWEEP_BATCH_SIZE]
    )
    for refund_id in candidate_ids:
        execute_refund_task.delay(refund_id)
    return len(candidate_ids)


@shared_task(**TASK_OPTIONS)
def scrub_expired_payment_audit_metadata():
    from apps.payments.models import Payment

    cutoff = timezone.now() - timedelta(days=settings.PAYMENT_AUDIT_RETENTION_DAYS)
    scrubbed_count = 0
    scrubbed_at = timezone.now()
    for _batch_number in range(SCRUB_MAX_BATCHES):
        candidate_ids = list(
            Payment.objects.filter(audit_scrubbed_at__isnull=True, created_at__lt=cutoff)
            .filter(Q(initiator_ip__isnull=False) | Q(first_callback_ip__isnull=False) | ~Q(initiator_user_agent=""))
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:SWEEP_BATCH_SIZE]
        )
        if not candidate_ids:
            break
        scrubbed_count += Payment.objects.filter(pk__in=candidate_ids).update(
            initiator_ip=None,
            first_callback_ip=None,
            initiator_user_agent="",
            audit_scrubbed_at=scrubbed_at,
        )
        if len(candidate_ids) < SWEEP_BATCH_SIZE:
            break
    return scrubbed_count
