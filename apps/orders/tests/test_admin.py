import pytest
from uuid import uuid4
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME

from apps.orders.models import Order
from apps.users.models import CustomUser
from apps.users.tests.factories import AddressFactory, UserFactory
from apps.cart.models import Cart, CartItem
from apps.orders.services.checkout import create_waiting_order
from apps.products.models import Product
from apps.products.tests.factories import ProductFactory


pytestmark = pytest.mark.django_db


def _request(user):
    request = RequestFactory().get("/admin/orders/order/")
    request.user = user
    return request


def _order_for(user):
    address = AddressFactory(user=user)
    return Order.objects.create_waiting(
        user=user, source_address=address,
        idempotency_key=uuid4(),
        subtotal="1.00", shipping_amount="0.00", total="1.00",
    )


def test_order_admin_hides_privileged_owner_orders_from_delegated_staff():
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_order", "change_order")))
    ordinary = UserFactory()
    staff_owner = UserFactory(is_staff=True)
    superuser_owner = UserFactory(is_staff=True, is_superuser=True)
    ordinary_order = _order_for(ordinary)
    staff_order = _order_for(staff_owner)
    _order_for(superuser_owner)
    model_admin = admin.site._registry[Order]

    queryset = model_admin.get_queryset(_request(delegated))

    assert list(queryset.values_list("pk", flat=True)) == [ordinary_order.pk]
    assert model_admin.has_view_permission(_request(delegated), ordinary_order)
    assert not model_admin.has_view_permission(_request(delegated), staff_order)


def test_order_admin_superuser_sees_all_owner_types():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    ordinary = _order_for(UserFactory())
    privileged = _order_for(UserFactory(is_staff=True))
    model_admin = admin.site._registry[Order]
    assert set(model_admin.get_queryset(_request(superuser)).values_list("pk", flat=True)) >= {ordinary.pk, privileged.pk}


def test_custom_protected_bulk_actions_are_registered_instead_of_global_delete_selected():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    product_admin = admin.site._registry[__import__("apps.products.models", fromlist=["Product"]).Product]
    user_admin = admin.site._registry[CustomUser]
    assert "delete_selected" not in product_admin.get_actions(_request(superuser))
    assert "delete_selected_products" in product_admin.get_actions(_request(superuser))
    assert "delete_selected" not in user_admin.get_actions(_request(superuser))
    assert "delete_selected_users" in user_admin.get_actions(_request(superuser))


def _commercial_order(*, user=None, product=None):
    address = AddressFactory(user=user) if user else AddressFactory()
    product = product or ProductFactory(stock=2)
    cart = Cart.objects.create(user=address.user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    order, _ = create_waiting_order(user=address.user, address_id=address.pk, idempotency_key=uuid4())
    return order, product


@pytest.mark.parametrize(
    ("model", "action_name"),
    ((Product, "delete_selected_products"), (CustomUser, "delete_selected_users")),
)
def test_custom_bulk_delete_confirmation_post_deletes_safe_records(client, model, action_name):
    operator = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(operator)
    target = ProductFactory() if model is Product else UserFactory()
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
    first = client.post(url, {"action": action_name, ACTION_CHECKBOX_NAME: [str(target.pk)], "index": "0"})
    assert first.status_code == 200
    assert b"delete_selected" in first.content
    confirmed = client.post(url, {"action": "delete_selected", ACTION_CHECKBOX_NAME: [str(target.pk)], "post": "yes"}, follow=True)
    assert confirmed.status_code == 200
    assert not model.objects.filter(pk=target.pk).exists()


@pytest.mark.parametrize("model", (Product, CustomUser))
def test_custom_bulk_delete_confirmation_keeps_mixed_commercial_selection_atomic(client, model):
    operator = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(operator)
    if model is Product:
        protected_order, protected = _commercial_order()
        safe = ProductFactory()
    else:
        protected = UserFactory()
        protected_order, _ = _commercial_order(user=protected)
        safe = UserFactory()
    action_name = "delete_selected_products" if model is Product else "delete_selected_users"
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
    selected = [str(protected.pk), str(safe.pk)]
    assert client.post(url, {"action": action_name, ACTION_CHECKBOX_NAME: selected, "index": "0"}).status_code == 200
    response = client.post(url, {"action": "delete_selected", ACTION_CHECKBOX_NAME: selected, "post": "yes"}, follow=True)
    assert response.status_code == 200
    assert model.objects.filter(pk=protected.pk).exists()
    assert model.objects.filter(pk=safe.pk).exists()
    assert Order.objects.filter(pk=protected_order.pk).exists()
    assert "successfully deleted" not in response.content.decode().lower()


def test_order_admin_real_urls_enforce_privileged_owner_boundary(client):
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_order", "change_order")))
    ordinary = _order_for(UserFactory())
    staff_owned = _order_for(UserFactory(is_staff=True))
    superuser_owned = _order_for(UserFactory(is_staff=True, is_superuser=True))
    client.force_login(delegated)
    ordinary_url = reverse("admin:orders_order_change", args=[ordinary.pk])
    assert client.get(ordinary_url).status_code == 200
    for hidden in (staff_owned, superuser_owned):
        assert client.get(reverse("admin:orders_order_change", args=[hidden.pk])).status_code in (302, 404)

    action_response = client.post(
        reverse("admin:orders_order_changelist"),
        {"action": "mark_selected_shipped", ACTION_CHECKBOX_NAME: [str(staff_owned.pk)], "index": "0"},
        follow=True,
    )
    assert action_response.status_code == 200
    staff_owned.refresh_from_db()
    assert staff_owned.status == Order.Status.WAITING_FOR_PAYMENT

    superuser = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(superuser)
    assert client.get(reverse("admin:orders_order_change", args=[staff_owned.pk])).status_code == 200
    assert client.get(reverse("admin:orders_order_change", args=[superuser_owned.pk])).status_code == 200
