import pytest
from uuid import uuid4
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from apps.orders.models import Order
from apps.users.models import CustomUser
from apps.users.tests.factories import AddressFactory, UserFactory


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
