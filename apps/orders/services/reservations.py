from django.utils import timezone

from apps.orders.models import Order, OrderItem, StockReservation
from apps.products.models import Product


class ReservationIntegrityError(Exception):
    """An Order's reservation set is missing or has an impossible mixed state."""


class ReservationStateError(ReservationIntegrityError):
    """A complete but incompatible reservation lifecycle was requested."""


def lock_order_lines_and_reservations(*, order: Order):
    """Lock products in numeric order, then lines and their one-to-one reservations."""
    product_ids = list(
        OrderItem.objects.filter(order=order).order_by("product_id").values_list("product_id", flat=True)
    )
    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
    }
    items = list(
        OrderItem.objects.select_for_update().filter(order=order).order_by("product_id", "id")
    )
    reservations = {
        reservation.order_item_id: reservation
        for reservation in StockReservation.objects.select_for_update()
        .filter(order_item_id__in=[item.pk for item in items])
        .order_by("order_item_id")
    }
    return products, items, reservations


def _validate_reservation_set(*, products, items, reservations, operation: str) -> str:
    if len(items) != len(reservations) or any(item.pk not in reservations for item in items):
        raise ReservationIntegrityError("Every order item must have one reservation.")
    if any(item.product_id not in products for item in items):
        raise ReservationIntegrityError("An ordered product is missing.")
    states = {reservations[item.pk].status for item in items}
    if len(states) != 1:
        raise ReservationIntegrityError("Order reservations have mixed lifecycle states.")
    state = states.pop()
    if operation == "consume":
        if state == StockReservation.Status.RELEASED:
            return state
        if state not in {StockReservation.Status.ACTIVE, StockReservation.Status.CONSUMED}:
            raise ReservationIntegrityError("Order reservations have an invalid lifecycle state.")
    elif operation == "release":
        if state == StockReservation.Status.CONSUMED:
            raise ReservationStateError("Consumed reservations cannot be released.")
        if state not in {StockReservation.Status.ACTIVE, StockReservation.Status.RELEASED}:
            raise ReservationIntegrityError("Order reservations have an invalid lifecycle state.")
    return state


def get_reservation_set_state(*, order: Order, operation: str) -> str:
    products, items, reservations = lock_order_lines_and_reservations(order=order)
    return _validate_reservation_set(
        products=products, items=items, reservations=reservations, operation=operation
    )


def release_active_reservations(*, order: Order, reason: str) -> bool:
    """Release each active line once. The caller must have locked the order."""
    products, items, reservations = lock_order_lines_and_reservations(order=order)
    state = _validate_reservation_set(products=products, items=items, reservations=reservations, operation="release")
    if state == StockReservation.Status.RELEASED:
        return False
    released_any = False
    now = timezone.now()
    for item in items:
        reservation = reservations.get(item.pk)
        product = products[item.product_id]
        product.stock += item.quantity
        product.save(update_fields=("stock", "updated_at"))
        reservation.status = StockReservation.Status.RELEASED
        reservation.released_at = now
        reservation.release_reason = reason
        reservation.save(update_fields=("status", "released_at", "release_reason", "updated_at"))
        released_any = True
    return released_any


def consume_active_reservations(*, order: Order) -> bool:
    """Consume active reservations without touching Product.stock a second time."""
    _products, items, reservations = lock_order_lines_and_reservations(order=order)
    state = _validate_reservation_set(products=_products, items=items, reservations=reservations, operation="consume")
    if state == StockReservation.Status.CONSUMED:
        return False
    if state == StockReservation.Status.RELEASED:
        return False
    now = timezone.now()
    consumed_any = False
    for item in items:
        reservation = reservations.get(item.pk)
        reservation.status = StockReservation.Status.CONSUMED
        reservation.consumed_at = now
        reservation.release_reason = ""
        reservation.save(update_fields=("status", "consumed_at", "release_reason", "updated_at"))
        consumed_any = True
    return consumed_any
