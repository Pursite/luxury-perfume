from django.utils import timezone

from apps.orders.models import Order, OrderItem, StockReservation
from apps.products.models import Product


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


def release_active_reservations(*, order: Order, reason: str) -> bool:
    """Release each active line once. The caller must have locked the order."""
    products, items, reservations = lock_order_lines_and_reservations(order=order)
    released_any = False
    now = timezone.now()
    for item in items:
        reservation = reservations.get(item.pk)
        if reservation is None or reservation.status != StockReservation.Status.ACTIVE:
            continue
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
    now = timezone.now()
    consumed_any = False
    for item in items:
        reservation = reservations.get(item.pk)
        if reservation is None or reservation.status != StockReservation.Status.ACTIVE:
            continue
        reservation.status = StockReservation.Status.CONSUMED
        reservation.consumed_at = now
        reservation.release_reason = ""
        reservation.save(update_fields=("status", "consumed_at", "release_reason", "updated_at"))
        consumed_any = True
    return consumed_any
