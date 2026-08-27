from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import (
    InvalidOrderTransitionError,
    confirm_verified_payment,
    expire_unpaid_order,
    mark_order_delivered,
    mark_order_shipped,
)
from apps.orders.services.reservations import ReservationIntegrityError
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


class OrderTransitionTests(TestCase):
    def _order_with_reservation(self):
        address = AddressFactory()
        product = ProductFactory(stock=3, price=Decimal("10.00"), discount_price=None)
        cart = Cart.objects.create(user=address.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order, _ = create_waiting_order(
            user=address.user, address_id=address.pk,
            idempotency_key="52e882cb-5bb5-4c02-9acc-3dd7873f3540",
        )
        return order, product

    def test_verified_payment_consumes_reservation_without_second_stock_decrement(self):
        order, product = self._order_with_reservation()

        confirm_verified_payment(order_id=order.pk)
        confirm_verified_payment(order_id=order.pk)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(order.items.get().reservation.status, StockReservation.Status.CONSUMED)

    def test_expiry_releases_stock_once_and_late_verified_payment_does_not_reactivate(self):
        order, product = self._order_with_reservation()
        expired_at = timezone.now() - timedelta(seconds=1)
        Order.objects.filter(pk=order.pk).update(
            created_at=expired_at - timedelta(minutes=15),
            reservation_expires_at=expired_at,
        )

        expire_unpaid_order(order_id=order.pk)
        confirm_verified_payment(order_id=order.pk)
        expire_unpaid_order(order_id=order.pk)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 3)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(order.late_payment_detected_at)
        self.assertEqual(order.items.get().reservation.status, StockReservation.Status.RELEASED)

    def test_only_processing_to_shipped_and_shipped_to_delivered_are_admin_transitions(self):
        order, _product = self._order_with_reservation()
        with self.assertRaises(InvalidOrderTransitionError):
            mark_order_shipped(order_id=order.pk)
        confirm_verified_payment(order_id=order.pk)
        mark_order_shipped(order_id=order.pk)
        mark_order_delivered(order_id=order.pk)
        with self.assertRaises(InvalidOrderTransitionError):
            mark_order_shipped(order_id=order.pk)

    def test_mixed_reservation_states_abort_expiry_without_partial_stock_restore(self):
        order, product = self._order_with_reservation()
        second = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
        from apps.orders.models import OrderItem
        second_item = OrderItem.objects.create_from_product(order=order, product=second, quantity=1)
        StockReservation.objects.create(order_item=second_item, status=StockReservation.Status.CONSUMED, consumed_at=timezone.now())
        expired_at = timezone.now() - timedelta(seconds=1)
        Order.objects.filter(pk=order.pk).update(created_at=expired_at - timedelta(minutes=15), reservation_expires_at=expired_at)

        with self.assertRaises(ReservationIntegrityError):
            expire_unpaid_order(order_id=order.pk)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertEqual(order.status, Order.Status.WAITING_FOR_PAYMENT)
