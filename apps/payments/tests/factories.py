import factory

from apps.orders.models import Order
from apps.payments.models import Payment, Refund
from apps.users.tests.factories import AddressFactory


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SelfAttribute("source_address.user")
    source_address = factory.SubFactory(AddressFactory)
    source_address_uuid = factory.SelfAttribute("source_address.pk")
    idempotency_key = factory.Faker("uuid4")
    status = Order.Status.WAITING_FOR_PAYMENT
    reservation_expires_at = factory.LazyFunction(
        lambda: __import__("django.utils.timezone", fromlist=["now"]).now()
        + __import__("datetime").timedelta(minutes=15)
    )
    subtotal = "100.00"
    shipping_amount = "0.00"
    total = "100.00"
    shipping_title = "Home"
    shipping_full_address = "Test address"


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory)
    provider = "fake"
    amount = factory.SelfAttribute("order.total")
    currency = "IRT"
    idempotency_key = factory.Faker("uuid4")
    initiator_ip = "198.51.100.10"
    initiator_user_agent = "test-agent"
    initiator_request_id = "a" * 32


class RefundFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Refund

    payment = factory.SubFactory(
        PaymentFactory,
        status=Payment.Status.VERIFIED,
        provider_session_id=factory.Sequence(lambda n: f"session-{n}"),
        provider_transaction_id=factory.Sequence(lambda n: f"transaction-{n}"),
        captured_amount="100.00",
        captured_currency="IRT",
        redirect_ready_at=factory.LazyFunction(
            lambda: __import__("django.utils.timezone", fromlist=["now"]).now()
        ),
        verified_at=factory.LazyFunction(
            lambda: __import__("django.utils.timezone", fromlist=["now"]).now()
        ),
    )
    provider = factory.SelfAttribute("payment.provider")
    reason = Refund.Reason.LATE_PAYMENT
    amount = factory.SelfAttribute("payment.captured_amount")
    currency = factory.SelfAttribute("payment.captured_currency")
