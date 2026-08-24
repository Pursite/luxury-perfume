from django.db.models import Prefetch

from apps.cart.models import CartItem
from apps.products.models import ProductImage
from apps.users.models import CustomUser


def get_cart_items_for_user(*, user: CustomUser) -> list[CartItem]:
    """Return one user's cart items with current Product and image data loaded."""
    queryset = (
        CartItem.objects.filter(cart__user=user)
        .select_related("product")
        .prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.order_by("display_order", "id"),
                to_attr="_cart_images",
            )
        )
        .order_by("created_at", "id")
    )
    return list(queryset)
