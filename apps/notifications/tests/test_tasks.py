from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.lib.sms.base import SmsSendOutcome, SmsSendResult, SmsTransportError
from apps.lib.sms.registry import register_provider
from apps.lib.tests.fakes import FakeSmsProvider
from apps.notifications.models import SmsDelivery
from apps.notifications.tasks import (
    execute_sms_delivery_task,
    scrub_expired_sms_recipients,
    sweep_due_sms_deliveries,
)
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


@override_settings(SMS_ENABLED=True, SMS_RECIPIENT_RETENTION_DAYS=180)
class SmsTaskTests(TestCase):
    def _delivery(self, *, status, recipient_phone=None, provider="test-sms", **values):
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
            "provider": provider,
            "status": status,
        }
        base.update(values)
        return SmsDelivery.objects.create(**base)

    @override_settings(SMS_PROVIDER="task-success")
    def test_delivery_task_returns_json_serializable_none_after_success(self):
        register_provider("task-success", FakeSmsProvider())
        delivery = self._delivery(
            status=SmsDelivery.Status.PENDING,
            provider="task-success",
            next_retry_at=timezone.now(),
        )

        result = execute_sms_delivery_task.run(delivery.pk)

        delivery.refresh_from_db()
        assert result is None
        assert json.dumps(result) == "null"
        assert delivery.status == SmsDelivery.Status.SENT

    @override_settings(SMS_PROVIDER="task-retry")
    def test_delivery_task_returns_none_after_retry(self):
        register_provider("task-retry", FakeSmsProvider(exception=SmsTransportError()))
        delivery = self._delivery(
            status=SmsDelivery.Status.PENDING,
            provider="task-retry",
            next_retry_at=timezone.now(),
        )

        result = execute_sms_delivery_task.run(delivery.pk)

        delivery.refresh_from_db()
        assert result is None
        assert delivery.status == SmsDelivery.Status.PENDING
        assert delivery.attempt_count == 1

    @override_settings(SMS_PROVIDER="task-failure")
    def test_delivery_task_returns_none_after_terminal_failure(self):
        register_provider(
            "task-failure",
            FakeSmsProvider(
                result=SmsSendResult(
                    outcome=SmsSendOutcome.REJECTED,
                    diagnostic_code="invalid_recipient",
                )
            ),
        )
        delivery = self._delivery(
            status=SmsDelivery.Status.PENDING,
            provider="task-failure",
            next_retry_at=timezone.now(),
        )

        result = execute_sms_delivery_task.run(delivery.pk)

        delivery.refresh_from_db()
        assert result is None
        assert delivery.status == SmsDelivery.Status.FAILED

    @override_settings(SMS_PROVIDER="task-manual-review")
    def test_delivery_task_returns_none_after_manual_review(self):
        provider = FakeSmsProvider(result=SmsSendResult(outcome=SmsSendOutcome.AMBIGUOUS))
        provider.supports_idempotent_send = False
        register_provider("task-manual-review", provider)
        delivery = self._delivery(
            status=SmsDelivery.Status.PENDING,
            provider="task-manual-review",
            next_retry_at=timezone.now(),
        )

        result = execute_sms_delivery_task.run(delivery.pk)

        delivery.refresh_from_db()
        assert result is None
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW

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

    def test_scrubbing_owner_phone_does_not_remove_owner_idempotency_identity(self):
        owner = UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)
        delivery = self._delivery(
            status=SmsDelivery.Status.SENT,
            recipient_phone=owner.phone_number,
            event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
            recipient_type=SmsDelivery.RecipientType.OWNER,
            recipient_user=owner,
            sent_at=timezone.now() - timedelta(days=181),
            provider_message_id="owner-message-123",
        )
        SmsDelivery.objects.filter(pk=delivery.pk).update(created_at=timezone.now() - timedelta(days=181))

        assert scrub_expired_sms_recipients.run() == 1

        delivery.refresh_from_db()
        assert delivery.recipient_phone is None
        assert delivery.recipient_user_id == owner.pk
        with self.assertRaises(IntegrityError):
            SmsDelivery.objects.create(
                order=delivery.order,
                event_type=SmsDelivery.EventType.OWNER_ORDER_PROCESSING,
                recipient_type=SmsDelivery.RecipientType.OWNER,
                recipient_user=owner,
                recipient_phone="09122222222",
                provider="test-sms",
                status=SmsDelivery.Status.PENDING,
                next_retry_at=timezone.now(),
            )
