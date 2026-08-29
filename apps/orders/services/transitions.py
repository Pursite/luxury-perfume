from dataclasses import dataclass
from enum import StrEnum

from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.reservations import (
    ReservationStateError,
    consume_active_reservations,
    get_reservation_set_state,
    release_active_reservations,
)


class InvalidOrderTransitionError(Exception):
    pass


class TransitionOutcome(StrEnum):
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"
    LATE_PAYMENT_REVIEW_REQUIRED = "late_payment_review_required"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class TransitionResult:
    order: Order | None
    previous_status: str | None
    current_status: str | None
    changed: bool
    outcome: TransitionOutcome

    def __getattr__(self, name):
        if self.order is not None:
            return getattr(self.order, name)
        raise AttributeError(name)


def _result(order, previous_status, changed, outcome):
    return TransitionResult(order, previous_status, order.status if order else None, changed, outcome)


@transaction.atomic
def expire_unpaid_order(*, order_id: int) -> TransitionResult:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        return _result(None, None, False, TransitionOutcome.NOT_FOUND)
    previous = order.status
    if order.status != Order.Status.WAITING_FOR_PAYMENT:
        return _result(order, previous, False, TransitionOutcome.ALREADY_APPLIED)
    if timezone.now() < order.reservation_expires_at:
        return _result(order, previous, False, TransitionOutcome.ALREADY_APPLIED)
    release_active_reservations(order=order, reason=Order.CancellationReason.RESERVATION_EXPIRED)
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = Order.CancellationReason.RESERVATION_EXPIRED
    order.cancelled_at = timezone.now()
    order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))
    return _result(order, previous, True, TransitionOutcome.APPLIED)


@transaction.atomic
def cancel_failed_payment(*, order_id: int) -> TransitionResult:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        return _result(None, None, False, TransitionOutcome.NOT_FOUND)
    previous = order.status
    if order.status == Order.Status.CANCELLED:
        return _result(order, previous, False, TransitionOutcome.ALREADY_APPLIED)
    if order.status != Order.Status.WAITING_FOR_PAYMENT:
        raise InvalidOrderTransitionError("Only waiting orders can be cancelled for payment failure.")
    reason = Order.CancellationReason.RESERVATION_EXPIRED if timezone.now() >= order.reservation_expires_at else Order.CancellationReason.PAYMENT_FAILED
    release_active_reservations(order=order, reason=reason)
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = reason
    order.cancelled_at = timezone.now()
    order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))
    return _result(order, previous, True, TransitionOutcome.APPLIED)


@transaction.atomic
def confirm_verified_payment(*, order_id: int) -> TransitionResult:
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        return _result(None, None, False, TransitionOutcome.NOT_FOUND)
    previous = order.status
    if order.status == Order.Status.WAITING_FOR_PAYMENT:
        if timezone.now() >= order.reservation_expires_at:
            release_active_reservations(order=order, reason=Order.CancellationReason.RESERVATION_EXPIRED)
            order.status = Order.Status.CANCELLED
            order.cancellation_reason = Order.CancellationReason.RESERVATION_EXPIRED
            order.cancelled_at = timezone.now()
            order.late_payment_detected_at = timezone.now()
            order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "late_payment_detected_at", "updated_at"))
            return _result(order, previous, True, TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED)
        reservation_state = get_reservation_set_state(order=order, operation="consume")
        if reservation_state == "released":
            order.status = Order.Status.CANCELLED
            order.cancellation_reason = Order.CancellationReason.PAYMENT_FAILED
            order.cancelled_at = timezone.now()
            order.late_payment_detected_at = timezone.now()
            order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "late_payment_detected_at", "updated_at"))
            return _result(order, previous, True, TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED)
        if reservation_state == "consumed":
            raise ReservationStateError("A waiting order cannot have consumed reservations.")
        consume_active_reservations(order=order)
        order.status = Order.Status.PROCESSING
        order.processing_at = timezone.now()
        order.save(update_fields=("status", "processing_at", "updated_at"))
        from apps.notifications.services.events import create_processing_sms_deliveries

        create_processing_sms_deliveries(order=order)
        return _result(order, previous, True, TransitionOutcome.APPLIED)
    elif order.status == Order.Status.CANCELLED:
        changed = order.late_payment_detected_at is None
        if changed:
            order.late_payment_detected_at = timezone.now()
            order.save(update_fields=("late_payment_detected_at", "updated_at"))
        return _result(order, previous, changed, TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED)
    if order.status == Order.Status.PROCESSING:
        if get_reservation_set_state(order=order, operation="consume") != "consumed":
            raise ReservationStateError("A processing order must have consumed reservations.")
    return _result(order, previous, False, TransitionOutcome.ALREADY_APPLIED)


@transaction.atomic
def mark_order_shipped(*, order_id: int) -> Order:
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PROCESSING:
        raise InvalidOrderTransitionError("Only processing orders can be shipped.")
    order.status = Order.Status.SHIPPED
    order.shipped_at = timezone.now()
    order.save(update_fields=("status", "shipped_at", "updated_at"))
    from apps.notifications.services.events import create_shipped_sms_delivery

    create_shipped_sms_delivery(order=order)
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
