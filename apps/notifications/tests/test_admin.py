from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.lib.tests.fakes import FakeSmsProvider
from apps.notifications.admin import SmsDeliveryAdmin
from apps.notifications.models import SmsDelivery
from apps.cart.models import Cart, CartItem
from apps.orders.services.checkout import create_waiting_order
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


class SmsDeliveryAdminTests(TestCase):
    def setUp(self):
        self.admin = SmsDeliveryAdmin(SmsDelivery, AdminSite())
        self.request = RequestFactory().get("/admin/notifications/smsdelivery/")

    def test_owner_recipient_identifier_is_read_only_and_never_exposes_phone(self):
        owner = UserFactory(phone_number="09121111111", is_staff=True, is_superuser=True)

        delivery = SimpleNamespace(recipient_user_id=owner.pk)
        identifier = self.admin.recipient_user_identifier(delivery)
        assert identifier == str(owner.pk)
        assert "recipient_user_identifier" in self.admin.readonly_fields
        assert "09121111111" not in identifier

    def _delivery_for(self, user):
        address = AddressFactory(user=user)
        product = ProductFactory(stock=2, price=Decimal("10.00"), discount_price=None)
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order, _ = create_waiting_order(
            user=user,
            address_id=address.pk,
            idempotency_key=str(uuid4()),
        )
        return SmsDelivery.objects.create(
            order=order,
            event_type=SmsDelivery.EventType.CUSTOMER_ORDER_CONFIRMED,
            recipient_type=SmsDelivery.RecipientType.CUSTOMER,
            recipient_phone="09129876543",
            provider="test-sms",
            status=SmsDelivery.Status.PENDING,
            next_retry_at=order.created_at,
        )

    def test_delegated_staff_cannot_list_staff_owned_orders_or_raw_recipient_fields(self):
        delegated_staff = UserFactory(is_staff=True, is_superuser=False)
        customer_delivery = self._delivery_for(UserFactory())
        staff_owned_delivery = self._delivery_for(UserFactory(is_staff=True, is_superuser=False))
        self.request.user = delegated_staff

        visible_ids = set(self.admin.get_queryset(self.request).values_list("pk", flat=True))
        fields = self.admin.get_fields(self.request, customer_delivery)

        assert visible_ids == {customer_delivery.pk}
        assert staff_owned_delivery.pk not in visible_ids
        assert "recipient_phone" not in fields
        assert "recipient_user" not in fields
        assert "provider_message_id" not in fields
        assert not self.admin.has_add_permission(self.request)
        assert not self.admin.has_delete_permission(self.request)

    def _delivery_for_manual_review(self, failure_code="attempts_exhausted"):
        delivery = self._delivery_for(UserFactory())
        delivery.status = SmsDelivery.Status.MANUAL_REVIEW
        delivery.attempt_count = 5
        delivery.manual_review_at = timezone.now()
        delivery.next_retry_at = None
        delivery.failure_code = failure_code
        delivery.save()
        return delivery

    def _retry_post(self, client, delivery, *, confirm=True):
        form = {"action": "rearm_selected_manual_review", ACTION_CHECKBOX_NAME: [str(delivery.pk)]}
        if confirm:
            form["confirm_sms_retry"] = "yes"
        else:
            form["index"] = "0"
        return client.post(reverse("admin:notifications_smsdelivery_changelist"), form)

    @override_settings(SMS_ENABLED=True)
    def test_sms_retry_requires_confirmation_and_audits_one_rearm(self):
        operator = UserFactory(is_staff=True, is_superuser=True)
        delivery = self._delivery_for_manual_review()
        self.client.force_login(operator)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(operator)
        assert self._retry_post(csrf_client, delivery).status_code == 403

        with (
            patch.dict("apps.lib.sms.registry._providers", {"test-sms": FakeSmsProvider()}),
            patch("apps.notifications.tasks.execute_sms_delivery_task.apply_async") as enqueue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            preview = self._retry_post(self.client, delivery, confirm=False)
            self.assertContains(preview, "Confirm SMS delivery retry")
            self.assertContains(preview, str(delivery.uuid))
            self.assertNotContains(preview, delivery.recipient_phone)
            delivery.refresh_from_db()
            assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
            assert not LogEntry.objects.filter(user=operator).exists()

            assert self._retry_post(self.client, delivery).status_code == 302
            assert self._retry_post(self.client, delivery).status_code == 302

        enqueue.assert_called_once_with(args=(delivery.pk,), countdown=0, retry=False)
        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.PENDING
        assert delivery.attempt_count == 5
        audit = LogEntry.objects.get(user=operator, action_flag=CHANGE)
        assert audit.content_type.model_class() is SmsDelivery
        assert audit.object_repr == str(delivery.uuid)
        assert audit.object_id == str(delivery.pk)

    def test_delegated_staff_cannot_retry_even_with_model_change_permission(self):
        operator = UserFactory(is_staff=True)
        operator.user_permissions.add(Permission.objects.get(codename="change_smsdelivery"))
        delivery = self._delivery_for_manual_review()
        self.client.force_login(operator)
        self.request.user = operator
        assert "rearm_selected_manual_review" not in self.admin.get_actions(self.request)
        self._retry_post(self.client, delivery)
        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
        assert not LogEntry.objects.filter(user=operator).exists()

    def test_disabled_invalid_and_non_idempotent_providers_do_not_rearm_ambiguous_deliveries(self):
        operator = UserFactory(is_staff=True, is_superuser=True)
        delivery = self._delivery_for_manual_review("ambiguous_non_idempotent")
        non_idempotent = FakeSmsProvider()
        non_idempotent.supports_idempotent_send = False
        self.client.force_login(operator)
        for enabled, providers in (
            (False, {"test-sms": FakeSmsProvider()}),
            (True, {}),
            (True, {"test-sms": FakeSmsProvider(configuration=("invalid",))}),
            (True, {"test-sms": non_idempotent}),
        ):
            with (
                self.subTest(enabled=enabled, providers=providers),
                override_settings(SMS_ENABLED=enabled),
                patch.dict("apps.lib.sms.registry._providers", providers, clear=True),
                self.captureOnCommitCallbacks(execute=True) as callbacks,
            ):
                assert self._retry_post(self.client, delivery).status_code == 302
                delivery.refresh_from_db()
                assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
                assert delivery.failure_code == "ambiguous_non_idempotent"
                assert not LogEntry.objects.filter(user=operator).exists()
            assert callbacks == []

    @override_settings(SMS_ENABLED=True)
    def test_sms_retry_rolls_back_rearm_and_enqueue_if_audit_fails(self):
        operator = UserFactory(is_staff=True, is_superuser=True)
        delivery = self._delivery_for_manual_review()
        self.client.force_login(operator)

        with (
            patch.dict("apps.lib.sms.registry._providers", {"test-sms": FakeSmsProvider()}),
            patch("apps.notifications.admin.LogEntry.objects.create", side_effect=RuntimeError("Audit failed")),
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            self.assertRaisesRegex(RuntimeError, "Audit failed"),
        ):
            self._retry_post(self.client, delivery)

        delivery.refresh_from_db()
        assert delivery.status == SmsDelivery.Status.MANUAL_REVIEW
        assert callbacks == []
