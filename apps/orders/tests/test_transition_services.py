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
    TransitionOutcome,
)
from apps.orders.services.reservations import ReservationIntegrityError, ReservationStateError
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

    def test_released_waiting_reservation_never_transitions_to_processing(self):
        order, product = self._order_with_reservation()
        reservation = order.items.get().reservation
        reservation.status = StockReservation.Status.RELEASED
        reservation.released_at = timezone.now()
        reservation.release_reason = StockReservation.ReleaseReason.PAYMENT_FAILED
        reservation.save()

        result = confirm_verified_payment(order_id=order.pk)

        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(result.outcome, TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(product.stock, 2)

    def test_waiting_consumed_and_processing_nonconsumed_states_are_rejected(self):
        order, _ = self._order_with_reservation()
        reservation = order.items.get().reservation
        reservation.status = StockReservation.Status.CONSUMED
        reservation.consumed_at = timezone.now()
        reservation.save()
        with self.assertRaises(ReservationStateError):
            confirm_verified_payment(order_id=order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.WAITING_FOR_PAYMENT)

        order.status = Order.Status.PROCESSING
        order.processing_at = timezone.now()
        order.save(update_fields=("status", "processing_at", "updated_at"))
        reservation.status = StockReservation.Status.ACTIVE
        reservation.consumed_at = None
        reservation.save()
        with self.assertRaises(ReservationStateError):
            confirm_verified_payment(order_id=order.pk)

        reservation.status = StockReservation.Status.RELEASED
        reservation.released_at = timezone.now()
        reservation.release_reason = StockReservation.ReleaseReason.PAYMENT_FAILED
        reservation.save()
        with self.assertRaises(ReservationStateError):
            confirm_verified_payment(order_id=order.pk)

    def test_processing_consumed_replay_and_late_callback_are_idempotent(self):
        order, product = self._order_with_reservation()
        applied = confirm_verified_payment(order_id=order.pk)
        replay = confirm_verified_payment(order_id=order.pk)
        self.assertEqual(applied.outcome, TransitionOutcome.APPLIED)
        self.assertEqual(replay.outcome, TransitionOutcome.ALREADY_APPLIED)
        self.assertFalse(replay.changed)

        second_order, second_product = self._order_with_reservation()
        expired_at = timezone.now() - timedelta(seconds=1)
        Order.objects.filter(pk=second_order.pk).update(created_at=expired_at - timedelta(minutes=15), reservation_expires_at=expired_at)
        first_late = confirm_verified_payment(order_id=second_order.pk)
        marker = first_late.order.late_payment_detected_at
        second_late = confirm_verified_payment(order_id=second_order.pk)
        second_order.refresh_from_db()
        product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(second_late.outcome, TransitionOutcome.LATE_PAYMENT_REVIEW_REQUIRED)
        self.assertFalse(second_late.changed)
        self.assertEqual(second_order.late_payment_detected_at, marker)
        self.assertEqual(second_product.stock, 3)

    def test_missing_reservation_aborts_confirmation(self):
        order, _ = self._order_with_reservation()
        order.items.get().reservation.delete()
        with self.assertRaises(ReservationIntegrityError):
            confirm_verified_payment(order_id=order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.WAITING_FOR_PAYMENT)
