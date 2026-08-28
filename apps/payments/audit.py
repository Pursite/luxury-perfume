"""Allowlisted financial lifecycle events for structured application logs."""

from typing import TYPE_CHECKING

from apps.lib.loggers import activity_logger


if TYPE_CHECKING:
    from apps.payments.models import Payment, Refund


EVENTS = frozenset({
    "payment_initialized",
    "payment_initiation_ambiguous",
    "payment_provider_error",
    "payment_callback_received",
    "payment_verification_succeeded",
    "payment_verification_failed",
    "payment_late",
    "payment_manual_review_required",
    "refund_queued",
    "refund_succeeded",
    "refund_retry_scheduled",
    "refund_manual_review_required",
})


def emit_payment_event(
    event: str,
    *,
    payment: "Payment | None" = None,
    refund: "Refund | None" = None,
    provider: str | None = None,
    outcome: str | None = None,
) -> None:
    """Log one fixed financial event with only safe correlation fields."""
    if event not in EVENTS:
        raise ValueError("Unknown payment audit event.")
    if payment is None and refund is not None:
        payment = refund.payment
    extra = {
        "category": "financial",
        "event": event,
        "payment_uuid": str(payment.uuid) if payment else None,
        "order_uuid": str(payment.order.uuid) if payment else None,
        "refund_uuid": str(refund.uuid) if refund else None,
        "provider": provider or (payment.provider if payment else None),
        "outcome": outcome,
    }
    activity_logger.info(event, extra=extra)
