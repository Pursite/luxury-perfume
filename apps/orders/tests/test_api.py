from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Order
from apps.users.tests.factories import AddressFactory


class OrderReadApiTests(APITestCase):
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
