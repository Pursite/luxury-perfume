from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.cart.models import Cart, CartItem
from apps.orders.config import get_shipping_flat_rate_irt
from apps.orders.models import Order, OrderItem, StockReservation
from apps.orders.services.reservations import release_active_reservations
from apps.products.models import Product
from apps.users.models import Address, CustomUser


class CheckoutError(Exception):
    pass


class CheckoutAddressError(CheckoutError):
    pass


class EmptyCartError(CheckoutError):
    pass


class ProductUnavailableError(CheckoutError):
    pass


class InsufficientStockError(CheckoutError):
    pass


class ActiveCheckoutError(CheckoutError):
    pass


class CheckoutUserInactiveError(CheckoutError):
    pass


class CheckoutProfileIncompleteError(CheckoutError):
    pass


class IdempotencyConflictError(CheckoutError):
    pass


class CheckoutUserNotFoundError(CheckoutError):
    pass


MAX_CART_ITEMS_FOR_CHECKOUT = 100


def _cancel_expired_locked_order(order: Order) -> None:
    release_active_reservations(order=order, reason=Order.CancellationReason.RESERVATION_EXPIRED)
    order.status = Order.Status.CANCELLED
    order.cancellation_reason = Order.CancellationReason.RESERVATION_EXPIRED
    order.cancelled_at = timezone.now()
    order.save(update_fields=("status", "cancellation_reason", "cancelled_at", "updated_at"))


def create_waiting_order(*, user: CustomUser, address_id, idempotency_key):
    """Create one paid-checkout candidate and atomically reserve current stock.

    An expired unswept waiting order is reconciled in its own committed transaction
    before a replacement checkout is attempted.
    """
    while True:
        retry_after_stale_reconciliation = False
        with transaction.atomic():
            try:
                locked_user = CustomUser.objects.select_for_update().get(pk=user.pk)
            except CustomUser.DoesNotExist as exc:
                raise CheckoutUserNotFoundError(_("The user no longer exists.")) from exc
            existing = (
                Order.objects.select_for_update().filter(user=locked_user, idempotency_key=idempotency_key).first()
            )
            now = timezone.now()
            if existing is not None:
                if existing.source_address_uuid != address_id:
                    raise IdempotencyConflictError(_("The idempotency key was used with another address."))
                if existing.status == Order.Status.WAITING_FOR_PAYMENT and now >= existing.reservation_expires_at:
                    _cancel_expired_locked_order(existing)
                return existing, False

            if not locked_user.is_active:
                raise CheckoutUserInactiveError(_("The user is inactive."))
            if not locked_user.is_profile_complete:
                raise CheckoutProfileIncompleteError(_("A complete profile and address are required."))

            waiting = (
                Order.objects.select_for_update().filter(user=locked_user, status=Order.Status.WAITING_FOR_PAYMENT).first()
            )
            if waiting is not None:
                if now < waiting.reservation_expires_at:
                    raise ActiveCheckoutError(_("An active checkout already exists."))
                _cancel_expired_locked_order(waiting)
                retry_after_stale_reconciliation = True
            else:
                address = Address.objects.select_for_update().filter(pk=address_id, user=locked_user).first()
                if address is None:
                    raise CheckoutAddressError(_("The address does not belong to the user."))
                cart = Cart.objects.select_for_update().filter(user=locked_user).first()
                if cart is None:
                    raise EmptyCartError(_("The cart is empty."))
                cart_item_ids = list(cart.items.order_by("product_id", "id").values_list("id", flat=True))
                if not cart_item_ids:
                    raise EmptyCartError(_("The cart is empty."))
                if len(cart_item_ids) > MAX_CART_ITEMS_FOR_CHECKOUT:
                    raise CheckoutError(_("The cart contains too many distinct products."))
                product_ids = list(CartItem.objects.filter(pk__in=cart_item_ids).order_by("product_id").values_list("product_id", flat=True))
                products = {
                    product.pk: product
                    for product in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
                }
                cart_items = list(CartItem.objects.select_for_update().filter(pk__in=cart_item_ids).order_by("product_id", "id"))
                if len(cart_items) != len(cart_item_ids):
                    raise EmptyCartError(_("The cart changed during checkout."))
                subtotal = Decimal("0.00")
                for cart_item in cart_items:
                    product = products.get(cart_item.product_id)
                    if product is None or not product.is_active:
                        raise ProductUnavailableError(_("A cart product is unavailable."))
                    if product.stock < cart_item.quantity:
                        raise InsufficientStockError(_("A cart product no longer has enough stock."))
                    subtotal += Decimal(str(product.final_price)) * cart_item.quantity
                shipping_amount = get_shipping_flat_rate_irt()
                total = subtotal + shipping_amount
                order = Order.objects.create_waiting(
                    user=locked_user,
                    source_address=address,
                    idempotency_key=idempotency_key,
                    subtotal=subtotal,
                    shipping_amount=shipping_amount,
                    total=total,
                )
                for cart_item in cart_items:
                    product = products[cart_item.product_id]
                    item = OrderItem.objects.create_from_product(order=order, product=product, quantity=cart_item.quantity)
                    StockReservation.objects.create(order_item=item)
                    product.stock -= cart_item.quantity
                    product.save(update_fields=("stock", "updated_at"))
                CartItem.objects.filter(pk__in=cart_item_ids).delete()
                cart.save(update_fields=("updated_at",))
                return order, True
        if not retry_after_stale_reconciliation:
            raise RuntimeError("Checkout loop exited without an outcome.")
