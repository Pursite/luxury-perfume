import pytest
from django.db import IntegrityError
from rest_framework.exceptions import AuthenticationFailed, Throttled, ValidationError

from apps.users.models import Address, CustomUser
from apps.users.selectors import UserSelector
from apps.users.services.login_otp_service import LoginOtpService
from apps.users.services.signup_service import SignupIdentityConflict, create_user_service
from apps.users.services.user_auth_service import UserAuthService
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def test_phone_selectors_normalize_before_lookup():
    user = CustomUser.objects.create_user(phone_number="09123456789")

    assert UserSelector.check_user_exists_by_phone(" 09123456789 ") is True
    assert UserSelector.get_user_by_phone(" 09123456789 ").pk == user.pk
    assert UserSelector.get_user_by_phone("09120000000") is None


def test_password_authentication_fails_generically_for_case_variant_duplicates():
    first = CustomUser.objects.create_user(
        username="LegacyUser",
        password="StrongPass123!",
    )
    second = CustomUser.objects.create_user(
        username="legacyuser",
        password="OtherStrongPass123!",
    )

    assert first.pk != second.pk
    with pytest.raises(
        AuthenticationFailed,
        match="Username or password is incorrect",
    ):
        UserSelector.authenticate_by_username_password(
            "LEGACYUSER",
            "StrongPass123!",
        )


def test_password_authentication_does_not_disclose_inactive_account_state():
    user = UserFactory(username="inactive_customer", is_active=False)
    user.set_password("CorrectHorseBatteryStaple42!")
    user.save(update_fields=["password"])

    with pytest.raises(
        AuthenticationFailed,
        match="Username or password is incorrect",
    ):
        UserSelector.authenticate_by_username_password(
            username=user.username,
            password="CorrectHorseBatteryStaple42!",
        )


def test_password_authentication_supports_legacy_mixed_case_username():
    user = CustomUser.objects.create_user(
        username="legacy_customer",
        password="CorrectHorseBatteryStaple42!",
    )
    CustomUser.objects.filter(pk=user.pk).update(username="Legacy_Customer")

    authenticated = UserSelector.authenticate_by_username_password(
        username="legacy_customer",
        password="CorrectHorseBatteryStaple42!",
    )

    assert authenticated.pk == user.pk


def test_signup_service_maps_manager_conflicts_to_generic_conflict():
    CustomUser.objects.create_user(
        username="existing_customer",
        password="CorrectHorseBatteryStaple42!",
    )

    with pytest.raises(SignupIdentityConflict):
        create_user_service(
            data={
                "username": "existing_customer",
                "password": "CorrectHorseBatteryStaple42!",
            }
        )


def test_password_login_success_clears_matching_failure_counter(settings):
    settings.PASSWORD_LOGIN_MAX_ATTEMPTS = 2
    settings.PASSWORD_LOGIN_LOCK_SECONDS = 60
    user = CustomUser.objects.create_user(
        username="lockable_user",
        password="StrongPass123!",
    )

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(
            user.username,
            "wrong-password",
            client_ip="198.51.100.10",
        )

    result = LoginOtpService.login_with_username_password(
        user.username,
        "StrongPass123!",
        client_ip="198.51.100.10",
    )

    assert set(result["tokens"]) == {"access", "refresh"}
    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(
            user.username,
            "wrong-password",
            client_ip="198.51.100.10",
        )


def test_password_login_lockout_is_scoped_to_username_and_client_ip(settings):
    settings.PASSWORD_LOGIN_MAX_ATTEMPTS = 2
    settings.PASSWORD_LOGIN_LOCK_SECONDS = 60
    first_user = CustomUser.objects.create_user(
        username="first_lock_user",
        password="StrongPass123!",
    )
    second_user = CustomUser.objects.create_user(
        username="second_lock_user",
        password="OtherStrongPass123!",
    )
    first_ip = "198.51.100.10"
    second_ip = "198.51.100.11"

    for _ in range(2):
        with pytest.raises(AuthenticationFailed):
            LoginOtpService.login_with_username_password(
                first_user.username,
                "wrong-password",
                client_ip=first_ip,
            )
    with pytest.raises(Throttled, match="Too many login attempts"):
        LoginOtpService.login_with_username_password(
            first_user.username,
            "StrongPass123!",
            client_ip=first_ip,
        )

    assert LoginOtpService.login_with_username_password(
        first_user.username,
        "StrongPass123!",
        client_ip=second_ip,
    )["tokens"]
    assert LoginOtpService.login_with_username_password(
        second_user.username,
        "OtherStrongPass123!",
        client_ip=first_ip,
    )["tokens"]


def test_complete_profile_rolls_back_user_when_address_creation_fails(mocker):
    user = UserFactory(
        username=None,
        email=None,
        first_name="",
        last_name="",
        is_active=True,
    )
    original_password = user.password
    validated_data = {
        "username": "rollback_user",
        "password": "StrongPass22!",
        "email": "rollback@example.com",
        "first_name": "Rollback",
        "last_name": "User",
        "address": {
            "title": "Home",
            "full_address": "Test address",
            "postal_code": "1234567890",
        },
    }
    mocker.patch.object(
        Address.objects,
        "create",
        side_effect=IntegrityError("simulated address constraint failure"),
    )

    with pytest.raises(
        ValidationError,
        match="Unable to update the profile",
    ):
        UserAuthService.complete_user_profile(
            user=user,
            validated_data=validated_data,
        )

    user.refresh_from_db()
    assert user.username is None
    assert user.email is None
    assert user.first_name == ""
    assert user.last_name == ""
    assert user.password == original_password
    assert Address.objects.filter(user=user).count() == 0
