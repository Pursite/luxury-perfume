from celery import shared_task
from django.db import InterfaceError, OperationalError
from django.utils import timezone
from kombu.exceptions import OperationalError as BrokerOperationalError

from apps.orders.models import Order
from apps.orders.services.transitions import expire_unpaid_order


RETRYABLE_EXCEPTIONS = (OperationalError, InterfaceError, BrokerOperationalError)
EXPIRY_BATCH_SIZE = 100
RETRY_OPTIONS = {
    "autoretry_for": RETRYABLE_EXCEPTIONS,
    "retry_backoff": 2,
    "retry_backoff_max": 30,
    "retry_jitter": True,
    "retry_kwargs": {"max_retries": 3},
}


@shared_task(**RETRY_OPTIONS)
def expire_unpaid_order_task(order_id: int):
    expire_unpaid_order(order_id=order_id)


@shared_task(**RETRY_OPTIONS)
def sweep_expired_orders() -> int:
    """Schedule database-authoritative expired waiting orders in bounded batches."""
    candidate_ids = list(
        Order.objects.filter(
            status=Order.Status.WAITING_FOR_PAYMENT,
            reservation_expires_at__lte=timezone.now(),
        )
        .order_by("reservation_expires_at", "id")
        .values_list("id", flat=True)[:EXPIRY_BATCH_SIZE]
    )
    for order_id in candidate_ids:
        expire_unpaid_order_task.delay(order_id)
    return len(candidate_ids)
