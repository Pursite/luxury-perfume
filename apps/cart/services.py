from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.products.models import Product
from apps.users.models import CustomUser


class CartItemNotFoundError(Exception):
    """Raised when the requested item does not belong to the user."""


class CartProductUnavailableError(Exception):
    """Raised when a product cannot currently be added to a cart."""


class CartStockExceededError(Exception):
    """Raised when a requested quantity exceeds current Product stock."""


def _lock_user(user: CustomUser) -> CustomUser:
    return CustomUser.objects.select_for_update().get(pk=user.pk)


def _get_locked_cart(*, user: CustomUser) -> Cart | None:
    return Cart.objects.select_for_update().filter(user=user).first()


def _touch_cart(cart: Cart) -> None:
    cart.save(update_fields=("updated_at",))


@transaction.atomic
def add_cart_item_service(
    *,
    user: CustomUser,
    product_slug: str,
    quantity: int,
) -> tuple[CartItem, bool]:
    """Add quantity to one active product while serializing this user's writes."""
    locked_user = _lock_user(user)
    product = Product.objects.filter(slug=product_slug, is_active=True).first()
    if product is None:
        raise CartProductUnavailableError
    if quantity > product.stock:
        raise CartStockExceededError

    cart = _get_locked_cart(user=locked_user)
    if cart is None:
        cart = Cart.objects.create(user=locked_user)

    item = (
        CartItem.objects.select_for_update()
        .filter(cart=cart, product=product)
        .first()
    )
    if item is None:
        item = CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=quantity,
        )
        created = True
    else:
        resulting_quantity = item.quantity + quantity
        if resulting_quantity > product.stock:
            raise CartStockExceededError
        item.quantity = resulting_quantity
        item.save(update_fields=("quantity", "updated_at"))
        created = False

    _touch_cart(cart)
    return item, created


@transaction.atomic
def update_cart_item_quantity_service(
    *,
    user: CustomUser,
    product_slug: str,
    quantity: int,
) -> CartItem:
    """Set an owned item's absolute quantity using current Product stock."""
    locked_user = _lock_user(user)
    cart = _get_locked_cart(user=locked_user)
    if cart is None:
        raise CartItemNotFoundError

    product = Product.objects.filter(slug=product_slug).first()
    if product is None:
        raise CartItemNotFoundError
    item = (
        CartItem.objects.select_for_update()
        .filter(cart=cart, product=product)
        .first()
    )
    if item is None:
        raise CartItemNotFoundError
    if quantity > product.stock:
        raise CartStockExceededError

    item.quantity = quantity
    item.save(update_fields=("quantity", "updated_at"))
    _touch_cart(cart)
    return item


@transaction.atomic
def remove_cart_item_service(
    *,
    user: CustomUser,
    product_slug: str,
) -> None:
    """Remove one item addressed only through its owner's cart and Product slug."""
    locked_user = _lock_user(user)
    cart = _get_locked_cart(user=locked_user)
    if cart is None:
        raise CartItemNotFoundError

    product = Product.objects.filter(slug=product_slug).first()
    if product is None:
        raise CartItemNotFoundError
    item = (
        CartItem.objects.select_for_update()
        .filter(cart=cart, product=product)
        .first()
    )
    if item is None:
        raise CartItemNotFoundError

    item.delete()
    _touch_cart(cart)


@transaction.atomic
def clear_cart_service(*, user: CustomUser) -> None:
    """Clear an existing cart without creating or deleting its container."""
    locked_user = _lock_user(user)
    cart = _get_locked_cart(user=locked_user)
    if cart is None:
        return

    cart.items.all().delete()
    _touch_cart(cart)
