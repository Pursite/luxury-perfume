import pytest
from uuid import uuid4
from django.contrib import admin
from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory
from django.urls import reverse
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.utils import timezone

from apps.orders.models import Order
from apps.notifications.models import SmsDelivery
from apps.users.models import CustomUser
from apps.users.tests.factories import AddressFactory, UserFactory
from apps.cart.models import Cart, CartItem
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import mark_order_shipped
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
    assert f'name="action" value="{action_name}"'.encode() in first.content
    confirmed = client.post(url, {"action": action_name, ACTION_CHECKBOX_NAME: [str(target.pk)], "post": "yes"}, follow=True)
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
    first = client.post(
        url,
        {"action": action_name, ACTION_CHECKBOX_NAME: selected, "index": "0"},
    )
    assert first.status_code == 200
    assert not first.context["perms_lacking"]
    assert f'name="action" value="{action_name}"'.encode() in first.content
    response = client.post(url, {"action": action_name, ACTION_CHECKBOX_NAME: selected, "post": "yes"}, follow=True)
    assert response.status_code == 200
    assert model.objects.filter(pk=protected.pk).exists()
    assert model.objects.filter(pk=safe.pk).exists()
    assert Order.objects.filter(pk=protected_order.pk).exists()
    assert "successfully deleted" not in response.content.decode().lower()
    assert "cannot be deleted" in response.content.decode().lower()
    assert not LogEntry.objects.filter(
        user=operator,
        action_flag=DELETION,
    ).exists()


@pytest.mark.parametrize("model", (Product, CustomUser))
def test_custom_bulk_delete_protected_selection_reports_error(client, model):
    operator = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(operator)
    if model is Product:
        protected_order, protected = _commercial_order()
    else:
        protected = UserFactory()
        protected_order, _ = _commercial_order(user=protected)
    action_name = (
        "delete_selected_products" if model is Product else "delete_selected_users"
    )
    url = reverse(
        f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
    )

    first = client.post(
        url,
        {
            "action": action_name,
            ACTION_CHECKBOX_NAME: [str(protected.pk)],
            "index": "0",
        },
    )
    assert first.status_code == 200
    assert not first.context["perms_lacking"]
    assert f'name="action" value="{action_name}"'.encode() in first.content
    response = client.post(
        url,
        {
            "action": action_name,
            ACTION_CHECKBOX_NAME: [str(protected.pk)],
            "post": "yes",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert model.objects.filter(pk=protected.pk).exists()
    assert Order.objects.filter(pk=protected_order.pk).exists()
    content = response.content.decode().lower()
    assert "cannot be deleted" in content
    assert "successfully deleted" not in content
    assert not LogEntry.objects.filter(
        user=operator,
        action_flag=DELETION,
    ).exists()


def test_order_admin_real_urls_enforce_privileged_owner_boundary(client):
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_order", "change_order")))
    ordinary = _order_for(UserFactory())
    staff_owned = _order_for(UserFactory(is_staff=True))
    superuser_owned = _order_for(UserFactory(is_staff=True, is_superuser=True))
    Order.objects.filter(pk=staff_owned.pk).update(
        status=Order.Status.PROCESSING,
        processing_at=timezone.now(),
    )
    staff_owned.refresh_from_db()
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
    assert staff_owned.status == Order.Status.PROCESSING

    superuser = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(superuser)
    assert client.get(reverse("admin:orders_order_change", args=[staff_owned.pk])).status_code == 200
    assert client.get(reverse("admin:orders_order_change", args=[superuser_owned.pk])).status_code == 200


def _processing_order():
    order, _product = _commercial_order()
    Order.objects.filter(pk=order.pk).update(status=Order.Status.PROCESSING, processing_at=timezone.now())
    order.refresh_from_db()
    return order


def _fulfillment_post(client, order, action):
    return client.post(
        reverse("admin:orders_order_changelist"),
        {"action": action, ACTION_CHECKBOX_NAME: [str(order.pk)], "index": "0"},
    )


def test_order_admin_view_permission_alone_cannot_ship_or_deliver(client):
    staff = UserFactory(is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="view_order"))
    client.force_login(staff)
    processing = _processing_order()
    shipped = _processing_order()
    Order.objects.filter(pk=shipped.pk).update(status=Order.Status.SHIPPED, shipped_at=timezone.now())

    actions = admin.site._registry[Order].get_actions(_request(staff))
    assert "mark_selected_shipped" not in actions
    assert "mark_selected_delivered" not in actions
    _fulfillment_post(client, processing, "mark_selected_shipped")
    _fulfillment_post(client, shipped, "mark_selected_delivered")
    processing.refresh_from_db()
    shipped.refresh_from_db()
    assert processing.status == Order.Status.PROCESSING
    assert shipped.status == Order.Status.SHIPPED
    assert not LogEntry.objects.filter(user=staff).exists()


def test_fulfillment_actions_require_csrf_and_audit_successful_transitions(client, settings):
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "order-admin-test"
    staff = UserFactory(is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="change_order"))
    order = _processing_order()
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(staff)
    assert _fulfillment_post(csrf_client, order, "mark_selected_shipped").status_code == 403
    order.refresh_from_db()
    assert order.status == Order.Status.PROCESSING

    client.force_login(staff)
    assert _fulfillment_post(client, order, "mark_selected_shipped").status_code == 302
    assert _fulfillment_post(client, order, "mark_selected_delivered").status_code == 302
    _fulfillment_post(client, order, "mark_selected_delivered")

    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED
    assert order.shipped_at and order.delivered_at
    assert SmsDelivery.objects.filter(order=order, event_type=SmsDelivery.EventType.CUSTOMER_ORDER_SHIPPED).count() == 1
    assert list(LogEntry.objects.filter(user=staff, object_id=str(order.pk), action_flag=CHANGE)
                .order_by("pk").values_list("change_message", flat=True)) == [
        "Order marked as shipped.", "Order marked as delivered.",
    ]


def test_fulfillment_rechecks_owner_after_order_was_selected():
    order = _processing_order()
    staff = UserFactory(is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="change_order"))
    request = RequestFactory().post(reverse("admin:orders_order_changelist"))
    request.user = staff
    model_admin = admin.site._registry[Order]
    CustomUser.objects.filter(pk=order.user_id).update(is_staff=True)

    # The supplied selection no longer reflects the current owner privileges.
    assert model_admin._apply_fulfillment(
        request, Order.objects.filter(pk=order.pk), Order.Status.PROCESSING,
        mark_order_shipped, "Order marked as shipped.",
    ) == 0
    order.refresh_from_db()
    assert order.status == Order.Status.PROCESSING
    assert not LogEntry.objects.filter(user=staff).exists()


def test_order_audit_failure_rolls_back_shipping_and_sms_outbox(client, mocker, settings):
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "order-admin-test"
    staff = UserFactory(is_staff=True, is_superuser=True)
    order = _processing_order()
    mocker.patch.object(admin.site._registry[Order], "log_change", side_effect=RuntimeError("Audit failed"))
    client.force_login(staff)

    with pytest.raises(RuntimeError, match="Audit failed"):
        _fulfillment_post(client, order, "mark_selected_shipped")

    order.refresh_from_db()
    assert order.status == Order.Status.PROCESSING
    assert not SmsDelivery.objects.filter(order=order).exists()
