from uuid import UUID

from apps.notifications.models import SmsDelivery


def order_reference(order_uuid: UUID) -> str:
    return order_uuid.hex[:12].upper()


def render_message(event_type: str, order_uuid: UUID) -> str:
    reference = order_reference(order_uuid)
    messages = {
        SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED: f"سفارش شما با موفقیت ثبت شد. کد سفارش: {reference}",
        SmsDelivery.EventType.OWNER_ORDER_PROCESSING: f"سفارش پرداخت‌شده جدید با کد {reference} آماده پردازش است.",
        SmsDelivery.EventType.CUSTOMER_ORDER_SHIPPED: f"سفارش {reference} به شرکت پست/حمل‌ونقل تحویل داده شد.",
    }
    try:
        return messages[event_type]
    except KeyError as exc:
        raise ValueError("Unknown SMS notification event.") from exc
