from decimal import Decimal

import pytest
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.payments.models import Payment
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    PaymentVerificationResult,
    VerificationOutcome,
)
from apps.payments.providers.registry import register_provider
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


pytestmark = pytest.mark.django_db


class ApiProvider:
    def __init__(self):
        self.create_calls = 0
        self.initiation = PaymentInitiationResult(
            outcome=InitiationOutcome.READY,
            provider_session_id="session-api",
            redirect_url="https://gateway.example.test/pay/session-api",
        )

    def create_payment(self, **kwargs):
        self.create_calls += 1
        return self.initiation

    def build_redirect_url(self, provider_session_id):
        return f"https://gateway.example.test/pay/{provider_session_id}"

    def parse_callback(self, *, method, query_params, data, headers):
        return query_params.get("session_id"), True

    def verify_payment(self, **kwargs):
        return PaymentVerificationResult(
            outcome=VerificationOutcome.VERIFIED,
            provider_transaction_id="transaction-api",
            captured_amount=Decimal("100.00"),
            captured_currency="IRT",
        )


@pytest.fixture
def api_provider(settings):
    adapter = ApiProvider()
    register_provider("fake-api", adapter)
    settings.PAYMENTS_ENABLED = True
    settings.PAYMENT_PROVIDER = "fake-api"
    settings.PAYMENT_CURRENCY = "IRT"
    settings.PAYMENT_PUBLIC_BASE_URL = "https://api.example.test"
    settings.PAYMENT_FRONTEND_RESULT_URL = "https://shop.example.test/payment-result"
    settings.PAYMENT_ALLOWED_REDIRECT_HOSTS = ("gateway.example.test",)
    return adapter


def _ready_user():
    address = AddressFactory()
    product = ProductFactory(stock=2, price=Decimal("100.00"), discount_price=None)
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return address


def _initialize(api_client, address, *, key="ec1fe0e8-26df-43db-a2bf-d0e31b8273eb"):
    api_client.force_authenticate(address.user)
    return api_client.post(
        reverse("payments:initialize"),
        {"address_uuid": str(address.pk)},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
        HTTP_USER_AGENT="safe browser",
        REMOTE_ADDR="198.51.100.7",
    )


def test_initialize_requires_authentication(api_client, api_provider):
    response = api_client.post(reverse("payments:initialize"), {}, format="json")

    assert response.status_code == 401


def test_initialize_returns_only_safe_server_derived_financial_fields(api_client, api_provider):
    address = _ready_user()

    response = _initialize(api_client, address)

    assert response.status_code == 201
    assert response.json()["payment"]["amount"] == "100.00"
    assert response.json()["payment"]["currency"] == "IRT"
    assert response.json()["redirect_url"] == "https://gateway.example.test/pay/session-api"
    encoded = response.content.decode()
    assert "session-api" not in encoded.replace(response.json()["redirect_url"], "")
    assert "transaction" not in encoded
    assert "provider" not in response.json()["payment"]


def test_initialize_rejects_client_controlled_financial_and_redirect_fields(api_client, api_provider):
    address = _ready_user()
    api_client.force_authenticate(address.user)

    response = api_client.post(
        reverse("payments:initialize"),
        {
            "address_uuid": str(address.pk),
            "amount": "1.00",
            "provider": "attacker",
            "return_url": "https://attacker.test",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="5b35c94d-1160-4eb8-97de-6b98d359e3fb",
    )

    assert response.status_code == 400
    assert api_provider.create_calls == 0


def test_ambiguous_initialize_returns_bounded_retry_guidance(api_client, api_provider):
    api_provider.initiation = PaymentInitiationResult(
        outcome=InitiationOutcome.AMBIGUOUS,
        diagnostic_code="transport_error",
    )
    address = _ready_user()

    response = _initialize(
        api_client,
        address,
        key="bcd64131-2c28-42e3-ac41-6d35b0248358",
    )

    assert response.status_code == 202
    assert response.json()["redirect_url"] is None
    assert response.json()["retry_after_seconds"] == 5
    assert response["Retry-After"] == "5"


def test_payment_status_is_owner_only_and_hides_provider_identifiers(api_client, api_provider):
    address = _ready_user()
    initialized = _initialize(api_client, address)
    payment_uuid = initialized.json()["payment"]["uuid"]

    owner_response = api_client.get(reverse("payments:detail", kwargs={"payment_uuid": payment_uuid}))
    api_client.force_authenticate(UserFactory())
    foreign_response = api_client.get(reverse("payments:detail", kwargs={"payment_uuid": payment_uuid}))

    assert owner_response.status_code == 200
    assert foreign_response.status_code == 404
    encoded = owner_response.content.decode()
    assert "session-api" not in encoded
    assert "transaction-api" not in encoded
    assert "198.51.100.7" not in encoded


def test_browser_callback_ignores_claimed_status_and_redirects_with_only_payment_uuid(api_client, api_provider):
    address = _ready_user()
    initialized = _initialize(api_client, address)
    payment_uuid = initialized.json()["payment"]["uuid"]
    api_client.force_authenticate(user=None)

    response = api_client.get(
        reverse("payments:callback", kwargs={"provider": "fake-api"}),
        {"session_id": "session-api", "success": "false", "return_url": "https://attacker.test"},
    )

    assert response.status_code == 303
    assert response["Location"] == f"https://shop.example.test/payment-result?payment_uuid={payment_uuid}"
    assert Payment.objects.get(uuid=payment_uuid).status == Payment.Status.VERIFIED
