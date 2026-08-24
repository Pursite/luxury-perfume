import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.products.models import Product
from apps.users.models import Address, CustomUser
from apps.users.tests.factories import AddressFactory, UserFactory


pytestmark = pytest.mark.django_db


def _admin_request(user):
    request = RequestFactory().post("/admin/users/customuser/")
    request.user = user
    return request


def _password_change_request(user):
    request = RequestFactory().post(
        "/admin/users/customuser/1/password/",
        data={
            "usable_password": "true",
            "password1": "ReplacementAdminPassword123!",
            "password2": "ReplacementAdminPassword123!",
        },
    )
    request.user = user
    SessionMiddleware(lambda current_request: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def _grant_permissions(user, *codenames):
    permissions = Permission.objects.filter(codename__in=codenames)
    user.user_permissions.add(*permissions)


def _creation_data(*, username="", phone_number="", is_active=True, password=True):
    data = {
        "username": username,
        "phone_number": phone_number,
        "email": "",
        "first_name": "Admin",
        "last_name": "Created",
        "usable_password": "true" if password else "false",
        "password1": "StrongAdminPassword123!" if password else "",
        "password2": "StrongAdminPassword123!" if password else "",
    }
    if is_active:
        data["is_active"] = "on"
    return data


@pytest.mark.parametrize(
    ("username", "phone_number"),
    [
        ("username_only_admin", ""),
        ("", "09123456781"),
        ("both_admin_identities", "09123456782"),
    ],
)
def test_user_admin_creation_supports_every_model_identity_and_hashes_password(
    username,
    phone_number,
):
    superuser = UserFactory(is_staff=True, is_superuser=True)
    user_admin = admin.site._registry[CustomUser]
    form_class = user_admin.get_form(_admin_request(superuser), obj=None)
    form = form_class(
        data=_creation_data(username=username, phone_number=phone_number)
    )

    assert form.is_valid(), form.errors
    user = form.save()

    assert user.username == (username or None)
    assert user.phone_number == (phone_number or None)
    assert user.check_password("StrongAdminPassword123!") is True
    assert user.password != "StrongAdminPassword123!"


def test_user_admin_creation_allows_identityless_inactive_user_with_no_password():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    user_admin = admin.site._registry[CustomUser]
    form_class = user_admin.get_form(_admin_request(superuser), obj=None)
    form = form_class(data=_creation_data(is_active=False, password=False))

    assert form.is_valid(), form.errors
    user = form.save()

    assert user.is_active is False
    assert user.has_identity is False
    assert user.has_usable_password() is False


def test_user_admin_creation_rejects_active_user_without_identity():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    user_admin = admin.site._registry[CustomUser]
    form_class = user_admin.get_form(_admin_request(superuser), obj=None)
    form = form_class(data=_creation_data())

    assert form.is_valid() is False
    assert "An active user must have a username or phone number." in str(
        form.non_field_errors()
    )


def test_user_admin_creation_requires_staff_access_for_superuser():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    user_admin = admin.site._registry[CustomUser]
    form_class = user_admin.get_form(_admin_request(superuser), obj=None)
    form = form_class(
        data={
            **_creation_data(username="invalid_superuser"),
            "is_superuser": "on",
        }
    )

    assert form.is_valid() is False
    assert form.errors["is_staff"] == [
        "A superuser must also have admin-site access."
    ]


def test_ordinary_staff_forms_cannot_submit_privilege_fields():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    _grant_permissions(
        ordinary_staff,
        "add_customuser",
        "change_customuser",
        "view_customuser",
    )
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(ordinary_staff)
    privilege_fields = {"is_staff", "is_superuser", "groups", "user_permissions"}

    add_form = user_admin.get_form(request, obj=None)
    change_form = user_admin.get_form(request, obj=customer)

    assert privilege_fields.isdisjoint(add_form.base_fields)
    assert privilege_fields.isdisjoint(change_form.base_fields)


def test_ordinary_staff_cannot_forge_privileges_during_user_creation():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    _grant_permissions(ordinary_staff, "add_customuser")
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(ordinary_staff)
    form_class = user_admin.get_form(request, obj=None)
    form = form_class(
        data={
            **_creation_data(username="forged_privileges"),
            "is_staff": "on",
            "is_superuser": "on",
        }
    )

    assert form.is_valid(), form.errors
    user = form.save(commit=False)
    user_admin.save_model(request, user, form, change=False)

    user.refresh_from_db()
    assert user.is_staff is False
    assert user.is_superuser is False


def test_ordinary_staff_cannot_access_privileged_user_objects():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    other_staff = UserFactory(is_staff=True, is_superuser=False)
    superuser = UserFactory(is_staff=True, is_superuser=True)
    _grant_permissions(
        ordinary_staff,
        "view_customuser",
        "change_customuser",
        "delete_customuser",
    )
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(ordinary_staff)
    visible_ids = set(
        user_admin.get_queryset(request).values_list("pk", flat=True)
    )

    assert customer.pk in visible_ids
    assert ordinary_staff.pk not in visible_ids
    assert other_staff.pk not in visible_ids
    assert superuser.pk not in visible_ids
    assert user_admin.has_view_permission(request, other_staff) is False
    assert user_admin.has_change_permission(request, other_staff) is False
    assert user_admin.has_delete_permission(request, superuser) is False


def test_customer_deactivation_blacklists_refresh_tokens():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    _grant_permissions(ordinary_staff, "change_customuser")
    RefreshToken.for_user(customer)
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(ordinary_staff)
    form_class = user_admin.get_form(request, obj=customer)
    form = form_class(
        instance=customer,
        data={
            "phone_number": customer.phone_number,
            "username": customer.username,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
        },
    )

    assert form.is_valid(), form.errors
    user = form.save(commit=False)
    user_admin.save_model(request, user, form, change=True)

    customer.refresh_from_db()
    assert customer.is_active is False
    assert BlacklistedToken.objects.filter(token__user=customer).exists() is True


def test_ordinary_staff_can_reactivate_customer_with_identity():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_active=False, is_staff=False, is_superuser=False)
    _grant_permissions(ordinary_staff, "change_customuser")
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(ordinary_staff)
    form_class = user_admin.get_form(request, obj=customer)
    form = form_class(
        instance=customer,
        data={
            "phone_number": customer.phone_number,
            "username": customer.username,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "is_active": "on",
        },
    )

    assert form.is_valid(), form.errors
    user = form.save(commit=False)
    user_admin.save_model(request, user, form, change=True)

    customer.refresh_from_db()
    assert customer.is_active is True


def test_admin_password_change_hashes_password_and_revokes_refresh_tokens():
    customer = UserFactory(is_staff=False, is_superuser=False)
    customer.set_password("OriginalAdminPassword123!")
    customer.save(update_fields=["password"])
    RefreshToken.for_user(customer)
    user_admin = admin.site._registry[CustomUser]
    form = user_admin.change_password_form(
        customer,
        data={
            "usable_password": "true",
            "password1": "ReplacementAdminPassword123!",
            "password2": "ReplacementAdminPassword123!",
        },
    )

    assert form.is_valid(), form.errors
    saved_user = form.save()

    saved_user.refresh_from_db()
    assert saved_user.check_password("ReplacementAdminPassword123!") is True
    assert BlacklistedToken.objects.filter(token__user=saved_user).exists() is True


def test_admin_can_disable_password_and_revoke_refresh_tokens():
    customer = UserFactory(is_staff=False, is_superuser=False)
    customer.set_password("OriginalAdminPassword123!")
    customer.save(update_fields=["password"])
    RefreshToken.for_user(customer)
    user_admin = admin.site._registry[CustomUser]
    form = user_admin.change_password_form(
        customer,
        data={"usable_password": "false"},
    )

    assert form.is_valid(), form.errors
    saved_user = form.save()

    saved_user.refresh_from_db()
    assert saved_user.has_usable_password() is False
    assert BlacklistedToken.objects.filter(token__user=saved_user).exists() is True


def test_superuser_can_manage_staff_groups_and_direct_permissions():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    customer = UserFactory(is_staff=False, is_superuser=False)
    group = Group.objects.create(name="Store managers")
    product_permission = Permission.objects.get(codename="view_product")
    user_admin = admin.site._registry[CustomUser]
    request = _admin_request(superuser)
    form_class = user_admin.get_form(request, obj=customer)
    form = form_class(
        instance=customer,
        data={
            "phone_number": customer.phone_number,
            "username": customer.username,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "is_active": "on",
            "is_staff": "on",
            "is_superuser": "on",
            "groups": [str(group.pk)],
            "user_permissions": [str(product_permission.pk)],
        },
    )

    assert {"is_staff", "is_superuser", "groups", "user_permissions"}.issubset(
        form_class.base_fields
    )
    assert form.is_valid(), form.errors
    user = form.save(commit=False)
    user_admin.save_model(request, user, form, change=True)
    form.save_m2m()

    customer.refresh_from_db()
    assert customer.is_staff is True
    assert customer.is_superuser is True
    assert list(customer.groups.all()) == [group]
    assert list(customer.user_permissions.all()) == [product_permission]


def test_ordinary_staff_update_rechecks_concurrent_privilege_elevation():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    stale_customer = CustomUser.objects.get(pk=customer.pk)
    _grant_permissions(ordinary_staff, "change_customuser")
    CustomUser.objects.filter(pk=customer.pk).update(is_staff=True)
    stale_customer.first_name = "Unauthorized change"

    with pytest.raises(PermissionDenied):
        admin.site._registry[CustomUser].save_model(
            _admin_request(ordinary_staff),
            stale_customer,
            form=None,
            change=True,
        )

    customer.refresh_from_db()
    assert customer.is_staff is True
    assert customer.first_name != "Unauthorized change"


def test_ordinary_staff_password_change_rechecks_concurrent_privilege_elevation(
    mocker,
):
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    customer.set_password("OriginalAdminPassword123!")
    customer.save(update_fields=["password"])
    stale_customer = CustomUser.objects.get(pk=customer.pk)
    _grant_permissions(ordinary_staff, "change_customuser")
    CustomUser.objects.filter(pk=customer.pk).update(is_staff=True)
    user_admin = admin.site._registry[CustomUser]
    mocker.patch.object(user_admin, "get_object", return_value=stale_customer)

    with pytest.raises(Http404):
        user_admin.user_change_password(
            _password_change_request(ordinary_staff),
            str(customer.pk),
        )

    customer.refresh_from_db()
    assert customer.is_staff is True
    assert customer.check_password("OriginalAdminPassword123!") is True


def test_ordinary_staff_single_delete_rechecks_concurrent_privilege_elevation():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    stale_customer = CustomUser.objects.get(pk=customer.pk)
    _grant_permissions(ordinary_staff, "delete_customuser")
    CustomUser.objects.filter(pk=customer.pk).update(is_staff=True)

    with pytest.raises(PermissionDenied):
        admin.site._registry[CustomUser].delete_model(
            _admin_request(ordinary_staff),
            stale_customer,
        )

    assert CustomUser.objects.filter(pk=customer.pk, is_staff=True).exists() is True


def test_ordinary_staff_bulk_delete_rechecks_concurrent_privilege_elevation():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    _grant_permissions(ordinary_staff, "delete_customuser")
    user_admin = admin.site._registry[CustomUser]
    selected_ids = list(
        user_admin.get_queryset(_admin_request(ordinary_staff))
        .filter(pk=customer.pk)
        .values_list("pk", flat=True)
    )
    CustomUser.objects.filter(pk=customer.pk).update(is_staff=True)

    with pytest.raises(PermissionDenied):
        user_admin.delete_queryset(
            _admin_request(ordinary_staff),
            CustomUser.objects.filter(pk__in=selected_ids),
        )

    assert CustomUser.objects.filter(pk=customer.pk, is_staff=True).exists() is True


def test_group_admin_is_superuser_only_even_with_group_permissions():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    _grant_permissions(
        ordinary_staff,
        "view_group",
        "add_group",
        "change_group",
        "delete_group",
    )
    group_admin = admin.site._registry[Group]
    request = _admin_request(ordinary_staff)

    assert group_admin.has_module_permission(request) is False
    assert group_admin.has_view_permission(request) is False
    assert group_admin.has_add_permission(request) is False
    assert group_admin.has_change_permission(request) is False
    assert group_admin.has_delete_permission(request) is False


def test_group_admin_remains_available_to_superusers():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    group_admin = admin.site._registry[Group]
    request = _admin_request(superuser)

    assert group_admin.has_module_permission(request) is True
    assert group_admin.has_view_permission(request) is True
    assert group_admin.has_add_permission(request) is True
    assert group_admin.has_change_permission(request) is True
    assert group_admin.has_delete_permission(request) is True


def test_is_staff_alone_does_not_grant_product_permissions():
    staff_user = UserFactory(is_staff=True, is_superuser=False)
    request = _admin_request(staff_user)

    assert admin.site._registry[Product].has_view_permission(request) is False


def test_superuser_address_admin_can_manage_privileged_user_addresses():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    privileged_user = UserFactory(is_staff=True, is_superuser=False)
    privileged_address = AddressFactory(user=privileged_user)
    address_admin = admin.site._registry[Address]
    request = _admin_request(superuser)
    form_class = address_admin.get_form(request, obj=None)

    assert address_admin.get_queryset(request).filter(
        pk=privileged_address.pk
    ).exists()
    assert form_class.base_fields["user"].queryset.filter(
        pk=privileged_user.pk
    ).exists()
    assert address_admin.has_view_permission(request, privileged_address) is True
    assert address_admin.has_change_permission(request, privileged_address) is True
    assert address_admin.has_delete_permission(request, privileged_address) is True

    privileged_address.title = "Managed by superuser"
    address_admin.save_model(
        request,
        privileged_address,
        form=None,
        change=True,
    )
    privileged_address.refresh_from_db()
    assert privileged_address.title == "Managed by superuser"


def test_ordinary_staff_address_admin_preserves_customer_address_lifecycle():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    _grant_permissions(
        ordinary_staff,
        "add_address",
        "change_address",
        "delete_address",
    )
    address_admin = admin.site._registry[Address]
    request = _admin_request(ordinary_staff)
    address = Address(
        user=customer,
        title="Customer address",
        full_address="Eligible customer address",
    )

    address_admin.save_model(request, address, form=None, change=False)
    address.title = "Updated customer address"
    address_admin.save_model(request, address, form=None, change=True)
    address.refresh_from_db()
    assert address.title == "Updated customer address"

    address_admin.delete_model(request, address)
    assert Address.objects.filter(pk=address.pk).exists() is False


def test_ordinary_staff_address_queryset_excludes_privileged_users():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer_address = AddressFactory()
    staff_address = AddressFactory(
        user=UserFactory(is_staff=True, is_superuser=False)
    )
    superuser_address = AddressFactory(
        user=UserFactory(is_staff=True, is_superuser=True)
    )
    _grant_permissions(ordinary_staff, "view_address")
    visible_ids = set(
        admin.site._registry[Address]
        .get_queryset(_admin_request(ordinary_staff))
        .values_list("pk", flat=True)
    )

    assert customer_address.pk in visible_ids
    assert staff_address.pk not in visible_ids
    assert superuser_address.pk not in visible_ids


def test_ordinary_staff_address_form_only_offers_customer_users():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    customer = UserFactory(is_staff=False, is_superuser=False)
    staff_user = UserFactory(is_staff=True, is_superuser=False)
    superuser = UserFactory(is_staff=True, is_superuser=True)
    _grant_permissions(ordinary_staff, "add_address")
    form_class = admin.site._registry[Address].get_form(
        _admin_request(ordinary_staff),
        obj=None,
    )
    selectable_ids = set(
        form_class.base_fields["user"].queryset.values_list("pk", flat=True)
    )

    assert customer.pk in selectable_ids
    assert staff_user.pk not in selectable_ids
    assert superuser.pk not in selectable_ids


def test_ordinary_staff_cannot_view_change_or_delete_privileged_address():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    privileged_address = AddressFactory(
        user=UserFactory(is_staff=True, is_superuser=False)
    )
    _grant_permissions(
        ordinary_staff,
        "view_address",
        "change_address",
        "delete_address",
    )
    address_admin = admin.site._registry[Address]
    request = _admin_request(ordinary_staff)

    assert address_admin.has_view_permission(request, privileged_address) is False
    assert address_admin.has_change_permission(request, privileged_address) is False
    assert address_admin.has_delete_permission(request, privileged_address) is False


def test_ordinary_staff_crafted_address_form_rejects_privileged_owner():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    privileged_user = UserFactory(is_staff=True, is_superuser=False)
    _grant_permissions(ordinary_staff, "add_address")
    form_class = admin.site._registry[Address].get_form(
        _admin_request(ordinary_staff),
        obj=None,
    )
    form = form_class(
        data={
            "user": str(privileged_user.pk),
            "title": "Restricted",
            "full_address": "Privileged account address",
            "postal_code": "1234567890",
        }
    )

    assert form.is_valid() is False
    assert "user" in form.errors


def test_ordinary_staff_address_save_rejects_privileged_owner_server_side():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    privileged_user = UserFactory(is_staff=True, is_superuser=False)
    _grant_permissions(ordinary_staff, "add_address")
    address = Address(
        user=privileged_user,
        title="Restricted",
        full_address="Privileged account address",
    )

    with pytest.raises(PermissionDenied):
        admin.site._registry[Address].save_model(
            _admin_request(ordinary_staff),
            address,
            form=None,
            change=False,
        )

    assert Address.objects.filter(pk=address.pk).exists() is False


def test_ordinary_staff_address_save_rejects_privileged_owner_change():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    address = AddressFactory()
    original_user_id = address.user_id
    privileged_user = UserFactory(is_staff=True, is_superuser=True)
    _grant_permissions(ordinary_staff, "change_address")
    address.user = privileged_user

    with pytest.raises(PermissionDenied):
        admin.site._registry[Address].save_model(
            _admin_request(ordinary_staff),
            address,
            form=None,
            change=True,
        )

    address.refresh_from_db()
    assert address.user_id == original_user_id


def test_ordinary_staff_address_update_rechecks_owner_privilege_at_write_time():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    address = AddressFactory()
    stale_address = Address.objects.get(pk=address.pk)
    _grant_permissions(ordinary_staff, "change_address")
    CustomUser.objects.filter(pk=address.user_id).update(is_staff=True)
    stale_address.title = "Unauthorized update"

    with pytest.raises(PermissionDenied):
        admin.site._registry[Address].save_model(
            _admin_request(ordinary_staff),
            stale_address,
            form=None,
            change=True,
        )

    address.refresh_from_db()
    assert address.title != "Unauthorized update"


def test_ordinary_staff_address_delete_rechecks_owner_privilege_at_write_time():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    address = AddressFactory()
    stale_address = Address.objects.get(pk=address.pk)
    _grant_permissions(ordinary_staff, "delete_address")
    CustomUser.objects.filter(pk=address.user_id).update(is_staff=True)

    with pytest.raises(PermissionDenied):
        admin.site._registry[Address].delete_model(
            _admin_request(ordinary_staff),
            stale_address,
        )

    assert Address.objects.filter(pk=address.pk).exists() is True


def test_ordinary_staff_address_bulk_delete_rechecks_owner_privilege():
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    address = AddressFactory()
    _grant_permissions(ordinary_staff, "delete_address")
    address_admin = admin.site._registry[Address]
    selected_ids = list(
        address_admin.get_queryset(_admin_request(ordinary_staff))
        .filter(pk=address.pk)
        .values_list("pk", flat=True)
    )
    CustomUser.objects.filter(pk=address.user_id).update(is_staff=True)

    with pytest.raises(PermissionDenied):
        address_admin.delete_queryset(
            _admin_request(ordinary_staff),
            Address.objects.filter(pk__in=selected_ids),
        )

    assert Address.objects.filter(pk=address.pk).exists() is True
