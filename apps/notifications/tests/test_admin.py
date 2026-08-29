from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

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
