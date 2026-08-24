from decimal import Decimal

from rest_framework import serializers

from apps.cart.models import CartItem
from apps.products.models import Product
from apps.products.serializers import ProductImageOutputSerializer


class CartItemAddInputSerializer(serializers.Serializer):
    product_slug = serializers.SlugField(max_length=280)
    quantity = serializers.IntegerField(min_value=1)


class CartItemQuantityInputSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartProductOutputSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("uuid", "slug", "name", "primary_image")
        read_only_fields = fields

    def get_primary_image(self, product: Product):
        images = getattr(product, "_cart_images", None)
        if images is None:
            images = list(product.images.order_by("display_order", "id"))
        image = next((item for item in images if item.is_primary), None)
        image = image or (images[0] if images else None)
        if image is None:
            return None
        return ProductImageOutputSerializer(image, context=self.context).data


class CartItemOutputSerializer(serializers.ModelSerializer):
    product = CartProductOutputSerializer(read_only=True)
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    line_total = serializers.DecimalField(
        max_digits=24,
        decimal_places=2,
        read_only=True,
    )
    available_stock = serializers.IntegerField(read_only=True)
    available = serializers.BooleanField(read_only=True)

    class Meta:
        model = CartItem
        fields = (
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "available_stock",
            "available",
        )
        read_only_fields = fields


class CartOutputSerializer(serializers.Serializer):
    items = CartItemOutputSerializer(many=True, read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=None,
        decimal_places=2,
        read_only=True,
    )
    has_unavailable_items = serializers.BooleanField(read_only=True)

    def to_representation(self, items):
        items = list(items)
        total_quantity = sum(item.quantity for item in items)
        total_price = sum(
            (item.line_total for item in items),
            start=Decimal("0.00"),
        )
        return {
            "items": CartItemOutputSerializer(
                items,
                many=True,
                context=self.context,
            ).data,
            "total_quantity": total_quantity,
            "total_price": self.fields["total_price"].to_representation(total_price),
            "has_unavailable_items": any(not item.available for item in items),
        }
