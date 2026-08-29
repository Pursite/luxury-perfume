import logging


_logger = logging.getLogger("activity")
_EVENTS = {
    "notification_created",
    "sms_delivery_started",
    "sms_delivery_succeeded",
    "sms_delivery_retry_scheduled",
    "sms_delivery_failed",
    "sms_manual_review_required",
    "sms_enqueue_failed",
}


def emit_notification_event(
    event,
    *,
    delivery=None,
    order=None,
    notification_uuid=None,
    order_uuid=None,
    event_type=None,
    provider=None,
    attempt=None,
    outcome=None,
):
    if event not in _EVENTS:
        raise ValueError("Unknown notification audit event.")
    order = order or (delivery.order if delivery is not None else None)
    extra = {"category": "activity", "event": event}
    if delivery is not None:
        extra.update(
            notification_uuid=str(delivery.uuid),
            event_type=delivery.event_type,
            attempt=delivery.attempt_count,
        )
    elif notification_uuid is not None:
        extra["notification_uuid"] = str(notification_uuid)
        if event_type is not None:
            extra["event_type"] = event_type
    if order is not None:
        extra["order_uuid"] = str(order.uuid)
    elif order_uuid is not None:
        extra["order_uuid"] = str(order_uuid)
    if provider:
        extra["provider"] = provider
    if attempt is not None:
        extra["attempt"] = attempt
    if outcome:
        extra["outcome"] = outcome
    _logger.info(event, extra=extra)
