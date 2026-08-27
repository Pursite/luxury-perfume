from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.reservations import consume_active_reservations, release_active_reservations


class InvalidOrderTransitionError(Exception):
    pass


@transaction.atomic
def expire_unpaid_order(*, order_id: int) -> Order | None:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None or order.status != Order.Status.WAITING_FOR_PAYMENT:
        return order
    if timezone.now() < order.reservation_expires_at:
        return order
    release_active_reservations(order=order, reason=Order.CancellationReason.RESERVATION_EXPIRED)
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = Order.CancellationReason.RESERVATION_EXPIRED
    order.cancelled_at = timezone.now()
    order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))
    return order


@transaction.atomic
def cancel_failed_payment(*, order_id: int) -> Order | None:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None or order.status != Order.Status.WAITING_FOR_PAYMENT:
        return order
    reason = Order.CancellationReason.RESERVATION_EXPIRED if timezone.now() >= order.reservation_expires_at else Order.CancellationReason.PAYMENT_FAILED
    release_active_reservations(order=order, reason=reason)
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = reason
    order.cancelled_at = timezone.now()
    order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))
    return order


@transaction.atomic
def confirm_verified_payment(*, order_id: int) -> Order | None:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        return None
    if order.status == Order.Status.WAITING_FOR_PAYMENT:
        if timezone.now() >= order.reservation_expires_at:
            release_active_reservations(order=order, reason=Order.CancellationReason.RESERVATION_EXPIRED)
            order.status = Order.Status.CANCELLED
            order.cancellation_reason = Order.CancellationReason.RESERVATION_EXPIRED
            order.cancelled_at = timezone.now()
            order.late_payment_detected_at = timezone.now()
            order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "late_payment_detected_at", "updated_at"))
            return order
        consume_active_reservations(order=order)
        order.status = Order.Status.PROCESSING
        order.processing_at = timezone.now()
        order.save(update_fields=("status", "processing_at", "updated_at"))
    elif order.status == Order.Status.CANCELLED:
        order.late_payment_detected_at = order.late_payment_detected_at or timezone.now()
        order.save(update_fields=("late_payment_detected_at", "updated_at"))
    return order


@transaction.atomic
def mark_order_shipped(*, order_id: int) -> Order:
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PROCESSING:
        raise InvalidOrderTransitionError("Only processing orders can be shipped.")
    order.status = Order.Status.SHIPPED
    order.shipped_at = timezone.now()
    order.save(update_fields=("status", "shipped_at", "updated_at"))
    return order


@transaction.atomic
def mark_order_delivered(*, order_id: int) -> Order:
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.SHIPPED:
        raise InvalidOrderTransitionError("Only shipped orders can be delivered.")
    order.status = Order.Status.DELIVERED
    order.delivered_at = timezone.now()
    order.save(update_fields=("status", "delivered_at", "updated_at"))
    return order
