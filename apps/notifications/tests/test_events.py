from decimal import Decimal

from django.db import transaction
from django.test import TestCase, override_settings

from apps.cart.models import Cart, CartItem
from apps.notifications.models import SmsDelivery
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import confirm_verified_payment, mark_order_shipped
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


@override_settings(SMS_ENABLED=True, SMS_PROVIDER="fake")
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

    def test_processing_without_eligible_superusers_creates_only_customer_delivery(self):
        order = self._order()

        confirm_verified_payment(order_id=order.pk)

        deliveries = SmsDelivery.objects.filter(order=order).order_by("event_type")
        assert list(deliveries.values_list("event_type", "recipient_type")) == [
            ("CUSTOMER_ORDER_CONFIRMED", "CUSTOMER"),
        ]

    def test_processing_creates_one_owner_delivery_per_eligible_superuser(self):
        owner_one = UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)
        owner_two = UserFactory(phone_number="09122222222", is_staff=True, is_superuser=True)
        UserFactory(phone_number=None, is_active=True, is_staff=True, is_superuser=True)
        UserFactory(phone_number="not-a-phone", is_staff=True, is_superuser=True)
        UserFactory(phone_number="09123333333", is_active=False, is_staff=True, is_superuser=True)
        UserFactory(phone_number="09124444444", is_staff=True, is_superuser=False)
        order = self._order()

        confirm_verified_payment(order_id=order.pk)

        owner_deliveries = SmsDelivery.objects.filter(
            order=order,
            event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
        )
        assert set(owner_deliveries.values_list("recipient_user_id", "recipient_phone")) == {
            (owner_one.pk, "09121111111"),
            (owner_two.pk, "09122222222"),
        }

    def test_replayed_processing_does_not_duplicate_customer_or_owner_deliveries(self):
        owner_one = UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)
        owner_two = UserFactory(phone_number="09122222222", is_staff=True, is_superuser=True)
        order = self._order()

        confirm_verified_payment(order_id=order.pk)
        confirm_verified_payment(order_id=order.pk)

        assert SmsDelivery.objects.filter(
            order=order,
            event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
        ).count() == 1
        assert list(
            SmsDelivery.objects.filter(
                order=order,
                event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
            ).values_list("recipient_user_id", flat=True)
        ) == [owner_two.pk, owner_one.pk]

    def test_owner_delivery_keeps_phone_snapshot_after_owner_phone_changes(self):
        owner = UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)
        order = self._order()

        confirm_verified_payment(order_id=order.pk)
        owner.phone_number = "09122222222"
        owner.save(update_fields=("phone_number", "updated_at"))

        delivery = SmsDelivery.objects.get(
            order=order,
            event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
            recipient_user=owner,
        )
        assert delivery.recipient_phone == "09121111111"

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
        UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                confirm_verified_payment(order_id=order.pk)
                raise RuntimeError("force rollback")

        order.refresh_from_db()
        assert order.status == "waiting_for_payment"
        assert SmsDelivery.objects.filter(order=order).count() == 0
