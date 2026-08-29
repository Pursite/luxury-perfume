from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.notifications.models import SmsDelivery
from apps.notifications.tasks import scrub_expired_sms_recipients, sweep_due_sms_deliveries
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


@override_settings(SMS_ENABLED=True, SMS_RECIPIENT_RETENTION_DAYS=180)
class SmsTaskTests(TestCase):
    def _delivery(self, *, status, recipient_phone=None, **values):
        address = AddressFactory()
        recipient_phone = recipient_phone or address.user.phone_number
        product = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
        cart = Cart.objects.create(user=address.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order, _ = create_waiting_order(
            user=address.user,
            address_id=address.pk,
            idempotency_key="52e882cb-5bb5-4c02-9acc-3dd7873f3540",
        )
        base = {
            "order": order,
            "event_type": SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
            "recipient_type": SmsDelivery.RecipientType.CUSTOMER,
            "recipient_phone": recipient_phone,
            "provider": "test-sms",
            "status": status,
        }
        base.update(values)
        return SmsDelivery.objects.create(**base)

    def test_sweeper_queues_only_due_pending_deliveries(self):
        due = self._delivery(status=SmsDelivery.Status.PENDING, next_retry_at=timezone.now())
        self._delivery(
            status=SmsDelivery.Status.PENDING,
            next_retry_at=timezone.now() + timedelta(minutes=1),
        )
        with patch("apps.notifications.tasks.execute_sms_delivery_task.apply_async") as enqueue:
            count = sweep_due_sms_deliveries.run()

        assert count == 1
        enqueue.assert_called_once_with(args=(due.pk,), retry=False)

    def test_scrubber_removes_expired_terminal_recipient_only(self):
        old_sent = self._delivery(
            status=SmsDelivery.Status.SENT,
            sent_at=timezone.now() - timedelta(days=181),
            provider_message_id="message-123",
        )
        SmsDelivery.objects.filter(pk=old_sent.pk).update(created_at=timezone.now() - timedelta(days=181))
        pending = self._delivery(
            status=SmsDelivery.Status.PENDING,
            recipient_phone="09129876544",
            next_retry_at=timezone.now(),
        )
        SmsDelivery.objects.filter(pk=pending.pk).update(created_at=timezone.now() - timedelta(days=181))

        assert scrub_expired_sms_recipients.run() == 1

        old_sent.refresh_from_db()
        pending.refresh_from_db()
        assert old_sent.recipient_phone is None
        assert old_sent.audit_scrubbed_at is not None
        assert pending.recipient_phone == "09129876544"
