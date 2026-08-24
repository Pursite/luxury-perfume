import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from apps.cart.admin import CartAdmin, CartItemInline
from apps.cart.models import Cart
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _admin_request(user):
    request = RequestFactory().get("/admin/cart/cart/")
    request.user = user
    return request


def _grant_view_cart(user):
    user.user_permissions.add(Permission.objects.get(codename="view_cart"))


def test_cart_is_registered_with_read_only_admin():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    request = _admin_request(superuser)
    cart = CartFactory()
    cart_admin = admin.site._registry[Cart]

    assert isinstance(cart_admin, CartAdmin)
    assert cart_admin.has_view_permission(request, cart) is True
    assert cart_admin.has_add_permission(request) is False
    assert cart_admin.has_change_permission(request, cart) is False
    assert cart_admin.has_delete_permission(request, cart) is False


def test_cart_item_inline_is_read_only():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    request = _admin_request(superuser)
    inline = CartItemInline(Cart, admin.site)

    assert inline.get_readonly_fields(request) == (
        "product",
        "quantity",
        "created_at",
        "updated_at",
    )
    assert inline.has_add_permission(request) is False
    assert inline.has_change_permission(request) is False
    assert inline.has_delete_permission(request) is False


def test_delegated_staff_cannot_view_privileged_users_carts():
    delegated_staff = UserFactory(is_staff=True, is_superuser=False)
    _grant_view_cart(delegated_staff)
    customer_cart = CartFactory(user__is_staff=False, user__is_superuser=False)
    staff_cart = CartFactory(user__is_staff=True, user__is_superuser=False)
    superuser_cart = CartFactory(user__is_staff=True, user__is_superuser=True)
    cart_admin = admin.site._registry[Cart]
    request = _admin_request(delegated_staff)

    visible_ids = set(
        cart_admin.get_queryset(request).values_list("pk", flat=True)
    )

    assert customer_cart.pk in visible_ids
    assert staff_cart.pk not in visible_ids
    assert superuser_cart.pk not in visible_ids
    assert cart_admin.has_view_permission(request, customer_cart) is True
    assert cart_admin.has_view_permission(request, staff_cart) is False
    assert cart_admin.has_view_permission(request, superuser_cart) is False


def test_cart_admin_list_uses_one_query_for_users_and_item_counts(
    django_assert_num_queries,
):
    superuser = UserFactory(is_staff=True, is_superuser=True)
    first_cart = CartFactory()
    second_cart = CartFactory()
    CartItemFactory(cart=first_cart)
    CartItemFactory(cart=first_cart)
    CartItemFactory(cart=second_cart)
    cart_admin = admin.site._registry[Cart]

    with django_assert_num_queries(1):
        rows = [
            (str(cart.user), cart_admin.item_count(cart))
            for cart in cart_admin.get_queryset(_admin_request(superuser))
        ]

    assert sorted(count for _, count in rows) == [1, 2]


def test_cart_item_inline_eager_loads_products(django_assert_num_queries):
    superuser = UserFactory(is_staff=True, is_superuser=True)
    first = CartItemFactory()
    second = CartItemFactory()
    inline = CartItemInline(Cart, admin.site)

    with django_assert_num_queries(1):
        labels = [
            str(item.product)
            for item in inline.get_queryset(_admin_request(superuser)).filter(
                pk__in=(first.pk, second.pk)
            )
        ]

    assert len(labels) == 2
