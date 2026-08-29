from decimal import Decimal

from django.test import TestCase, override_settings
from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.notifications.models import SmsDelivery
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import confirm_verified_payment, mark_order_shipped
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


@override_settings(SMS_ENABLED=True, ORDER_PROCESSING_ALERT_PHONE="09123456789", SMS_PROVIDER="fake")
class NotificationTransitionTests(TestCase):
    def _order(self):
        address = AddressFactory(user__phone_number="09129876543")
        product = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
        cart = Cart.objects.create(user=address.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        return create_waiting_order(
            user=address.user,
            address_id=address.pk,
            idempotency_key="52e882cb-5bb5-4c02-9acc-3dd7873f3540",
        )[0]

    def test_applied_processing_transition_creates_one_customer_and_owner_delivery(self):
        order = self._order()

        confirm_verified_payment(order_id=order.pk)
        confirm_verified_payment(order_id=order.pk)

        deliveries = SmsDelivery.objects.filter(order=order).order_by("event_type")
        assert list(deliveries.values_list("event_type", "recipient_type")) == [
            ("CUSTOMER_ORDER_CONFIRMED", "CUSTOMER"),
            ("OWNER_ORDER_PROCESSING", "OWNER"),
        ]

    def test_shipped_transition_creates_one_customer_delivery(self):
        order = self._order()
        confirm_verified_payment(order_id=order.pk)

        mark_order_shipped(order_id=order.pk)

        assert SmsDelivery.objects.filter(
            order=order,
            event_type=SmsDelivery.EventType.CUSTOMER_ORDER_SHIPPED,
            recipient_type=SmsDelivery.RecipientType.CUSTOMER,
        ).count() == 1

    @override_settings(SMS_ENABLED=False)
    def test_disabled_sms_does_not_create_outbox_rows(self):
        order = self._order()

        confirm_verified_payment(order_id=order.pk)

        assert SmsDelivery.objects.filter(order=order).count() == 0

    def test_outer_transaction_rollback_discards_transition_outbox_rows(self):
        order = self._order()

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                confirm_verified_payment(order_id=order.pk)
                raise RuntimeError("force rollback")

        order.refresh_from_db()
        assert order.status == "waiting_for_payment"
        assert SmsDelivery.objects.filter(order=order).count() == 0
