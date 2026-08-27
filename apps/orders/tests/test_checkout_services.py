from decimal import Decimal

from django.test import TestCase

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


class CreateWaitingOrderTests(TestCase):
    def test_reserves_available_stock_snapshots_lines_and_clears_cart(self):
        """Removing the reservation write would leave stock and the cart incorrect."""
        address = AddressFactory()
        cart = Cart.objects.create(user=address.user)
        product = ProductFactory(stock=5, price=Decimal("100.00"), discount_price=None)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        order, created = create_waiting_order(
            user=address.user,
            address_id=address.pk,
            idempotency_key="b9538e55-d8d1-476c-bc5b-fc8a65c2b3ce",
        )

        product.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(order.status, Order.Status.WAITING_FOR_PAYMENT)
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(product.stock, 3)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())
        item = order.items.get()
        self.assertEqual(item.product_name, product.name)
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.line_total, Decimal("200.00"))
        self.assertEqual(item.reservation.status, StockReservation.Status.ACTIVE)
