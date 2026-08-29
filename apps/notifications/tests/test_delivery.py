from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from uuid import uuid4

from apps.cart.models import Cart, CartItem
from apps.lib.sms.base import SmsSendOutcome, SmsSendResult, SmsTransportError
from apps.lib.sms.registry import register_provider
from apps.lib.tests.fakes import FakeSmsProvider
from apps.notifications.models import SmsDelivery
from apps.notifications.services.delivery import execute_delivery, rearm_manual_delivery
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory


@override_settings(SMS_ENABLED=True, SMS_PROVIDER="test-sms")
class SmsDeliveryServiceTests(TestCase):
    def _delivery(self):
        address = AddressFactory(user__phone_number="09129876543")
        product = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
        cart = Cart.objects.create(user=address.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order, _ = create_waiting_order(
            user=address.user,
            address_id=address.pk,
            idempotency_key="52e882cb-5bb5-4c02-9acc-3dd7873f3540",
        )
        return SmsDelivery.objects.create(
            order=order,
            event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
            recipient_type=SmsDelivery.RecipientType.CUSTOMER,
            recipient_phone="09129876543",
            provider="test-sms",
            status=SmsDelivery.Status.PENDING,
            next_retry_at=timezone.now(),
        )

    def test_provider_acceptance_marks_delivery_sent_once(self):
        provider = FakeSmsProvider()
        register_provider("test-sms", provider)
        delivery = self._delivery()

        execute_delivery(delivery_id=delivery.pk)
        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.SENT
        assert delivery.provider_message_id == "fake-message-1"
        assert len(provider.calls) == 1

    def test_safe_transport_failure_schedules_a_retry(self):
        provider = FakeSmsProvider(exception=SmsTransportError())
        register_provider("test-sms", provider)
        delivery = self._delivery()

        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.PENDING
        assert delivery.attempt_count == 1
        assert delivery.next_retry_at > timezone.now()

    def test_non_idempotent_ambiguous_result_requires_manual_review(self):
        provider = FakeSmsProvider(result=SmsSendResult(outcome=SmsSendOutcome.AMBIGUOUS))
        provider.supports_idempotent_send = False
        register_provider("test-sms", provider)
        delivery = self._delivery()

        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
        assert delivery.failure_code == "ambiguous_non_idempotent"

    def test_provider_rejection_is_terminal_without_retry(self):
        register_provider(
            "test-sms",
            FakeSmsProvider(
                result=SmsSendResult(
                    outcome=SmsSendOutcome.REJECTED,
                    diagnostic_code="invalid_recipient",
                )
            ),
        )
        delivery = self._delivery()

        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.FAILED
        assert delivery.next_retry_at is None
        assert delivery.failure_code == "invalid_recipient"

    def test_missing_provider_moves_claimed_delivery_to_manual_review(self):
        delivery = self._delivery()
        delivery.provider = "not-registered"
        delivery.save(update_fields=("provider", "updated_at"))

        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
        assert delivery.failure_code == "provider_configuration"

    def test_stale_non_idempotent_lease_is_not_sent_again(self):
        provider = FakeSmsProvider()
        provider.supports_idempotent_send = False
        register_provider("test-sms", provider)
        delivery = self._delivery()
        delivery.status = SmsDelivery.Status.SENDING
        delivery.attempt_count = 1
        delivery.operation_token = uuid4()
        delivery.operation_started_at = timezone.now() - timedelta(seconds=31)
        delivery.last_attempt_at = delivery.operation_started_at
        delivery.next_retry_at = timezone.now() - timedelta(seconds=1)
        delivery.save()

        execute_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
        assert delivery.failure_code == "stale_non_idempotent_lease"
        assert provider.calls == []

    def test_superuser_rearm_preserves_attempt_history(self):
        delivery = self._delivery()
        delivery.status = SmsDelivery.Status.MANUAL_REVIEW
        delivery.attempt_count = 5
        delivery.next_retry_at = None
        delivery.manual_review_at = timezone.now()
        delivery.failure_code = "attempts_exhausted"
        delivery.save()

        rearm_manual_delivery(delivery_id=delivery.pk)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.PENDING
        assert delivery.attempt_count == 5
        assert delivery.next_retry_at is not None
