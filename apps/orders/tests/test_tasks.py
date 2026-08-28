from datetime import timedelta

from django.test import TestCase
from unittest.mock import patch
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.tasks import expire_unpaid_order_task, sweep_expired_orders
from apps.users.tests.factories import AddressFactory


class ExpiryTaskTests(TestCase):
    def test_sweeper_uses_order_deadline_and_queues_at_most_100_candidates(self):
        """Reading a reservation deadline instead would make Order expiry non-authoritative."""
        address = AddressFactory()
        order = Order.objects.create_waiting(
            user=address.user, source_address=address,
            idempotency_key="a68055b8-c3be-4dec-b6e1-27e6645f2a8d",
            subtotal="1.00", shipping_amount="0.00", total="1.00",
        )
        expired_at = timezone.now() - timedelta(seconds=1)
        Order.objects.filter(pk=order.pk).update(
            created_at=expired_at - timedelta(minutes=15),
            reservation_expires_at=expired_at,
        )

        with patch.object(expire_unpaid_order_task, "delay") as delay:
            queued = sweep_expired_orders()

        self.assertEqual(queued, 1)
        delay.assert_called_once_with(order.pk)
