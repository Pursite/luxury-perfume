from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.lib.basemodel import BaseModel
from apps.products.models import Product


class Cart(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )

    def __str__(self) -> str:
        return f"Cart for {self.user}"


class CartItem(BaseModel):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "product"),
                name="cart_unique_product_per_cart",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="cart_item_quantity_gte_1",
            ),
        ]

    @property
    def unit_price(self):
        return self.product.final_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def available_stock(self):
        return self.product.stock

    @property
    def available(self):
        return self.product.is_active and self.available_stock >= self.quantity

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity}"
