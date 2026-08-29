from decimal import Decimal

from django.test import TestCase, override_settings

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, StockReservation
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.checkout import (
    CheckoutAddressError,
    CheckoutProfileIncompleteError,
    CheckoutUserInactiveError,
    CheckoutUserNotFoundError,
    IdempotencyConflictError,
)
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


class CreateWaitingOrderTests(TestCase):
    def _ready_checkout(self):
        address = AddressFactory()
        product = ProductFactory(stock=5, price=Decimal("100.00"), discount_price=None)
        cart = Cart.objects.create(user=address.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        return address, product

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
        self.assertEqual(order.shipping_amount, Decimal("350000.00"))
        self.assertEqual(order.total, Decimal("350200.00"))
        self.assertEqual(product.stock, 3)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())
        item = order.items.get()
        self.assertEqual(item.product_name, product.name)
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.line_total, Decimal("200.00"))
        self.assertEqual(item.reservation.status, StockReservation.Status.ACTIVE)

    def test_new_checkout_revalidates_locked_user_and_address_readiness(self):
        inactive_address, _ = self._ready_checkout()
        inactive_address.user.is_active = False
        inactive_address.user.save(update_fields=("is_active", "updated_at"))
        with self.assertRaises(CheckoutUserInactiveError):
            create_waiting_order(user=inactive_address.user, address_id=inactive_address.pk, idempotency_key="509a94a5-0b96-4d26-bccb-e20ed87848db")

        incomplete_address, _ = self._ready_checkout()
        incomplete_address.user.first_name = ""
        incomplete_address.user.save(update_fields=("first_name", "updated_at"))
        with self.assertRaises(CheckoutProfileIncompleteError):
            create_waiting_order(user=incomplete_address.user, address_id=incomplete_address.pk, idempotency_key="c434b954-0eb3-442d-ac3c-6608fe3f8341")

        valid_address, _ = self._ready_checkout()
        foreign_address = AddressFactory()
        with self.assertRaises(CheckoutAddressError):
            create_waiting_order(user=valid_address.user, address_id=foreign_address.pk, idempotency_key="35dbf4d7-328e-4d9a-876b-4e9a7a78252a")

    def test_idempotent_replay_uses_immutable_address_identity_and_reserves_once(self):
        address, product = self._ready_checkout()
        key = "6ee9a3c6-d02b-4b12-9f5f-4ba4d2533e24"
        first, first_created = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key=key)
        second, second_created = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key=key)
        product.refresh_from_db()
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(product.stock, 4)

        other_address = AddressFactory(user=address.user)
        with self.assertRaises(IdempotencyConflictError):
            create_waiting_order(user=address.user, address_id=other_address.pk, idempotency_key=key)
        self.assertEqual(Order.objects.filter(user=address.user).count(), 1)

    @override_settings(ORDER_SHIPPING_FLAT_RATE_IRT="350000.00")
    def test_replay_keeps_its_original_shipping_snapshot_when_configuration_changes(self):
        """Reading the rate before idempotency replay would rewrite historical checkout semantics."""
        address, _ = self._ready_checkout()
        key = "7fe97c28-c525-46a2-90b0-0ebee60c9d49"
        first, created = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key=key)

        with override_settings(ORDER_SHIPPING_FLAT_RATE_IRT="400000.00"):
            replay, replay_created = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key=key)

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first.shipping_amount, Decimal("350000.00"))
        self.assertEqual(replay.shipping_amount, Decimal("350000.00"))
        self.assertEqual(replay.total, Decimal("350100.00"))

    def test_replay_survives_deleted_address_and_incomplete_current_profile(self):
        address, _ = self._ready_checkout()
        address_uuid = address.pk
        key = "4170d9e3-75ba-41e7-ad80-a6e5fa188059"
        order, _ = create_waiting_order(user=address.user, address_id=address_uuid, idempotency_key=key)
        address.delete()
        address.user.first_name = ""
        address.user.save(update_fields=("first_name", "updated_at"))

        replay, created = create_waiting_order(user=address.user, address_id=address_uuid, idempotency_key=key)

        self.assertFalse(created)
        self.assertEqual(replay.pk, order.pk)
        self.assertEqual(replay.source_address_uuid, address_uuid)

    def test_stale_deleted_user_maps_to_checkout_domain_error(self):
        address, _ = self._ready_checkout()
        stale_user = address.user
        stale_user.delete()
        with self.assertRaises(CheckoutUserNotFoundError):
            create_waiting_order(user=stale_user, address_id=address.pk, idempotency_key="be630760-143f-4e92-b1be-b2d99cbe82ae")
