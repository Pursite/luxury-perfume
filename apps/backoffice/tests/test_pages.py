from uuid import uuid4

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order
from apps.orders.services.checkout import create_waiting_order
from apps.payments.tests.factories import OrderFactory
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import AddressFactory, UserFactory


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("route", "args"),
    [
        ("dashboard", []), ("inventory", []),
        ("order_summary", [uuid4()]), ("customer_detail", [uuid4()]),
    ],
)
def test_backoffice_keeps_admin_login_and_permission_gate(client, staff_client, route, args):
    url = reverse(f"admin:backoffice:{route}", args=args)
    anonymous = client.get(url)
    assert anonymous.status_code == 302
    assert anonymous.url.startswith(reverse("admin:login"))
    client.force_login(UserFactory(is_staff=False))
    assert client.get(url).status_code == 302
    assert staff_client().get(url).status_code == 403


def test_admin_remains_english_without_changing_storefront_locale(staff_client):
    client = staff_client("orders.view_order")
    client.cookies["django_language"] = "fa"
    index = client.get(reverse("admin:index"))
    assert isinstance(admin.site._registry[Order], admin.ModelAdmin)
    assert index.headers["Content-Language"] == "en"
    assert b"Open store dashboard" in index.content
    response = client.get(reverse("admin:backoffice:dashboard"))
    assert response.headers["Content-Language"] == "en"
    assert b'lang="en"' in response.content
    assert b'dir="rtl"' not in response.content
    assert "no-store" in response.headers["Cache-Control"]
    assert client.get(reverse("health-live")).headers["Content-Language"] == "fa"
    login = Client().get(reverse("admin:login"), HTTP_ACCEPT_LANGUAGE="fa")
    assert login.headers["Content-Language"] == "en"


def test_print_summary_uses_immutable_checkout_snapshots(staff_client):
    client = staff_client("orders.view_order")
    customer = UserFactory(first_name="Original", last_name="Customer", email="original@example.test")
    address = AddressFactory(user=customer, title="Home", full_address="Original Shipping Address")
    product = ProductFactory(name="Original Fragrance", price="70.05", discount_price=None, stock=2)
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    order, _created = create_waiting_order(user=customer, address_id=address.pk, idempotency_key=uuid4())
    customer.first_name = "Renamed"
    customer.save(update_fields=["first_name"])
    product.name = "New Fragrance"
    product.price = "999.00"
    product.save(update_fields=["name", "price"])
    address.full_address = "New Shipping Address"
    address.save(update_fields=["full_address"])

    summary_url = reverse("admin:backoffice:order_summary", args=[order.uuid])
    change_url = reverse("admin:orders_order_change", args=[order.pk])
    assert summary_url.encode() in client.get(change_url).content
    response = client.get(summary_url)
    assert response.status_code == 200
    for text in (
        str(order.uuid), "Order Summary", "tax invoice", "Original Customer", "original@example.test",
        "Original Shipping Address", "Original Fragrance", "70.05", str(order.shipping_amount), str(order.total),
        "Waiting for payment",
    ):
        assert text.encode() in response.content
    for text in ("Renamed", "New Shipping Address", "New Fragrance", "999.00"):
        assert text.encode() not in response.content


@pytest.mark.parametrize("owner_flags", [{"is_staff": True}, {"is_superuser": True}])
def test_delegated_staff_cannot_access_protected_customers_or_order_summaries(staff_client, owner_flags):
    owner = UserFactory(**owner_flags)
    order = OrderFactory(source_address__user=owner)
    client = staff_client("users.view_customuser", "orders.view_order")
    assert client.get(reverse("admin:backoffice:customer_detail", args=[owner.pk])).status_code == 404
    assert client.get(reverse("admin:backoffice:order_summary", args=[order.uuid])).status_code == 404


def test_customer_history_requires_both_permissions_and_paginates_only_the_target_orders(staff_client):
    customer = UserFactory()
    unrelated = OrderFactory()
    address = AddressFactory(user=customer, title="Home")
    orders = OrderFactory.build_batch(
        51, source_address=address, status=Order.Status.PROCESSING, processing_at=timezone.now(),
    )
    Order.objects.bulk_create(orders)
    url = reverse("admin:backoffice:customer_detail", args=[customer.pk])
    client = staff_client("users.view_customuser")
    assert client.get(url).status_code == 403

    client = staff_client("users.view_customuser", "orders.view_order")
    assert url.encode() in client.get(reverse("admin:users_customuser_change", args=[customer.pk])).content
    first = client.get(url)
    second = client.get(url, {"page": 2})
    assert first.status_code == second.status_code == 200
    assert len(first.context["page"].object_list) == 50
    assert [order.pk for order in second.context["page"].object_list] == [orders[0].pk]
    assert str(unrelated.uuid).encode() not in first.content
    assert reverse("admin:orders_order_change", args=[orders[0].pk]).encode() in second.content


def test_inventory_filters_active_stock_paginates_and_keeps_threshold(staff_client):
    client = staff_client("products.view_product")
    named = ProductFactory(name="Low stock item", stock=1)
    ProductFactory(name="Hidden inactive item", stock=0, is_active=False)
    ProductFactory(name="Above threshold item", stock=2)
    ProductFactory.create_batch(50, stock=1, category=named.category, brand=named.brand)
    url = reverse("admin:backoffice:inventory")
    first = client.get(url, {"threshold": 1})
    second = client.get(url, {"threshold": 1, "page": 2})
    assert first.status_code == second.status_code == 200
    assert first.context["page"].paginator.count == 51
    assert len(first.context["page"].object_list) == 50
    assert len(second.context["page"].object_list) == 1
    assert b"threshold=1&amp;page=2" in first.content
    assert reverse("admin:products_product_change", args=[named.pk]).encode() in first.content + second.content
    assert b"Hidden inactive item" not in first.content
    assert b"Above threshold item" not in first.content
    assert client.get(url, {"threshold": -1}).status_code == 400
    assert b"No active products match" in client.get(url, {"threshold": 0}).content


def test_inventory_default_threshold_applies_without_query_parameters(staff_client):
    client = staff_client("products.view_product")
    low_stock = ProductFactory(stock=5)
    ProductFactory(stock=6)

    response = client.get(reverse("admin:backoffice:inventory"))
    assert response.status_code == 200
    assert response.context["form"]["threshold"].value() == 5
    assert [product.pk for product in response.context["page"]] == [low_stock.pk]
