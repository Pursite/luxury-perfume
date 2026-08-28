from rest_framework import serializers

from apps.orders.models import Order, OrderItem


class OrderItemOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("product_uuid", "product_name", "product_sku", "unit_price", "quantity", "line_total")


class OrderListOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("uuid", "status", "subtotal", "shipping_amount", "total", "reservation_expires_at", "created_at")


class OrderDetailOutputSerializer(OrderListOutputSerializer):
    items = OrderItemOutputSerializer(many=True, read_only=True)

    class Meta(OrderListOutputSerializer.Meta):
        fields = OrderListOutputSerializer.Meta.fields + (
            "customer_first_name", "customer_last_name", "customer_phone_number", "customer_email",
            "shipping_title", "shipping_full_address", "shipping_postal_code", "cancellation_reason",
            "processing_at", "shipped_at", "delivered_at", "cancelled_at", "items",
        )
