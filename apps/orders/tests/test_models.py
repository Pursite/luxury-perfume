from django.db import IntegrityError
from django.test import TestCase

from apps.orders.models import Order, OrderItem, StockReservation
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


class OrderModelTests(TestCase):
    def test_order_item_owns_reservation_quantity_and_order_owns_deadline(self):
        """A reservation must not duplicate the line quantity or order deadline."""
        address = AddressFactory()
        product = ProductFactory(price="80.00", discount_price="70.00")
        order = Order.objects.create_waiting(
            user=address.user,
            source_address=address,
            idempotency_key="3d1bbf54-26e8-4e55-8339-0fa5d49e29c1",
            subtotal="160.00",
            shipping_amount="0.00",
            total="160.00",
        )
        item = OrderItem.objects.create_from_product(
            order=order,
            product=product,
            quantity=2,
        )
        reservation = StockReservation.objects.create(order_item=item)

        self.assertEqual(item.quantity, 2)
        self.assertEqual(reservation.status, StockReservation.Status.ACTIVE)
        self.assertFalse(hasattr(reservation, "quantity"))
        self.assertFalse(hasattr(reservation, "expires_at"))
        self.assertIsNotNone(order.reservation_expires_at)

    def test_waiting_order_is_unique_per_user(self):
        address = AddressFactory()
        values = {
            "user": address.user,
            "source_address": address,
            "subtotal": "1.00",
            "shipping_amount": "0.00",
            "total": "1.00",
        }
        Order.objects.create_waiting(
            **values,
            idempotency_key="a840c777-c05e-4f8d-ae99-e97e7f2f5190",
        )

        with self.assertRaises(IntegrityError):
            Order.objects.create_waiting(
                **values,
                idempotency_key="6495196e-0b43-4ded-aa42-cbcfc46ef2af",
            )
