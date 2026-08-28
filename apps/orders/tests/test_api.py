from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Order
from apps.cart.models import Cart, CartItem
from apps.orders.selectors import get_user_order_detail_queryset
from apps.orders.serializers import OrderDetailOutputSerializer
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


class OrderReadApiTests(APITestCase):
    def _checkout(self, *, item_count=1):
        address = AddressFactory(title="Home", full_address="Original address", postal_code="1234567890")
        cart = Cart.objects.create(user=address.user)
        products = []
        for index in range(item_count):
            product = ProductFactory(name=f"Snapshot {index}", sku=f"SNAP-{index}-{address.pk}", stock=2, price="25.00", discount_price=None)
            CartItem.objects.create(cart=cart, product=product, quantity=1)
            products.append(product)
        order, _ = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key="9c158193-f62b-4f2b-a3c8-d346b0dbcc38")
        return order, address, products

    def test_list_returns_only_the_authenticated_users_orders(self):
        """Dropping owner filtering would disclose another customer's commercial record."""
        own_address = AddressFactory()
        other_address = AddressFactory()
        own_order = Order.objects.create_waiting(
            user=own_address.user,
            source_address=own_address,
            idempotency_key="8a8e4c55-12ba-4fc7-8f55-e70a228c555a",
            subtotal="1.00", shipping_amount="0.00", total="1.00",
        )
        Order.objects.create_waiting(
            user=other_address.user,
            source_address=other_address,
            idempotency_key="1840eef6-c30d-48b4-8f17-7287bf6f42dc",
            subtotal="1.00", shipping_amount="0.00", total="1.00",
        )
        self.client.force_authenticate(own_address.user)

        response = self.client.get("/api/v1/orders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(own_order.uuid))

    def test_detail_is_owner_only_and_uses_historical_snapshots(self):
        order, address, products = self._checkout()
        product = products[0]
        original_item = order.items.get()
        original_shipping = (
            order.shipping_title,
            order.shipping_full_address,
            order.shipping_postal_code,
        )
        product.name = "Changed product"
        product.sku = "CHANGED-SKU"
        product.price = "999.00"
        product.save(update_fields=("name", "sku", "price", "updated_at"))
        address.title = "Changed title"
        address.full_address = "Changed address"
        address.postal_code = "0987654321"
        address.save(
            update_fields=("title", "full_address", "postal_code", "updated_at")
        )
        address.delete()
        self.client.force_authenticate(order.user)

        response = self.client.get(f"/api/v1/orders/{order.uuid}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        line = response.data["items"][0]
        self.assertEqual(line["product_name"], original_item.product_name)
        self.assertEqual(line["product_sku"], original_item.product_sku)
        self.assertEqual(line["unit_price"], "25.00")
        self.assertEqual(line["line_total"], "25.00")
        self.assertEqual(
            (
                response.data["shipping_title"],
                response.data["shipping_full_address"],
                response.data["shipping_postal_code"],
            ),
            original_shipping,
        )
        order.refresh_from_db()
        self.assertIsNone(order.source_address_id)

        outsider = AddressFactory().user
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order.uuid}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_selector_prefetches_multiple_lines_without_n_plus_one(self):
        order, _address, _products = self._checkout(item_count=3)
        with self.assertNumQueries(2):
            selected = get_user_order_detail_queryset(user=order.user).get(pk=order.pk)
            data = OrderDetailOutputSerializer(selected).data
            self.assertEqual(len(data["items"]), 3)
