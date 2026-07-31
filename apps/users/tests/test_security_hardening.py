import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.test import APIClient

from apps.lib.security_cache import OTPVerificationGuard, SecurityCacheUnavailable
from apps.users.models import CustomUser
from apps.users.selectors import UserSelector
from apps.users.services.login_otp_service import LoginOtpService
from apps.users.services.signup_otp_service import SendOTPService
from apps.users.services.pass_reset_service import PasswordResetService
from apps.users.tests.factories import AddressFactory, UserFactory


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_user_requires_one_identity():
    user = CustomUser()
    with pytest.raises(DjangoValidationError):
        user.full_clean()


@pytest.mark.django_db
def test_manager_supports_password_only_and_phone_only_users():
    password_user = CustomUser.objects.create_user(username="PasswordUser", password="StrongPass123!")
    phone_user = CustomUser.objects.create_user(phone_number="09123456789")
    assert password_user.check_password("StrongPass123!")
    assert phone_user.has_usable_password() is False
    assert str(CustomUser(pk=123)) == "123"


@pytest.mark.django_db
def test_phone_selectors_normalize_before_lookup():
    user = CustomUser.objects.create_user(phone_number="09123456789")

    assert UserSelector.check_user_exists_by_phone(" 09123456789 ") is True
    assert UserSelector.get_user_by_phone(" 09123456789 ").pk == user.pk


@pytest.mark.django_db
def test_password_login_fails_generically_for_legacy_case_variant_duplicates():
    first = CustomUser.objects.create_user(
        username="LegacyUser",
        password="StrongPass123!",
    )
    second = CustomUser.objects.create_user(
        username="legacyuser",
        password="OtherStrongPass123!",
    )
    assert first.pk != second.pk

    with pytest.raises(AuthenticationFailed, match="Username or password is incorrect"):
        UserSelector.authenticate_by_username_password("LEGACYUSER", "StrongPass123!")


@pytest.mark.django_db
def test_password_user_can_log_in_before_profile_completion():
    user = CustomUser.objects.create_user(username="login_now", password="StrongPass123!")
    assert user.is_profile_complete is False
    assert LoginOtpService.login_with_username_password("login_now", "StrongPass123!")["tokens"]
    AddressFactory(user=user)
    user.email, user.first_name, user.last_name = "user@example.com", "A", "B"
    user.save()
    assert user.is_profile_complete is True


@pytest.mark.django_db
def test_signup_otp_is_consumed_and_attempt_namespaces_are_isolated(mocker):
    mocker.patch("apps.users.services.signup_otp_service.send_otp_sms_task.delay")
    SendOTPService.send_signup_otp("09123456789")
    with pytest.raises(Exception):
        SendOTPService.verify_signup_otp("09123456789", "000000")
    mocker.patch.object(SendOTPService, "_generate_otp_code", return_value="123456")
    SendOTPService.send_signup_otp("09123456789")
    assert SendOTPService.verify_signup_otp("09123456789", "123456")["tokens"]
    with pytest.raises(Exception):
        SendOTPService.verify_signup_otp("09123456789", "123456")
    assert LoginOtpService._attempt_key("09123456789") != SendOTPService._attempt_key("09123456789")
    assert PasswordResetService._attempt_key("09123456789") != SendOTPService._attempt_key("09123456789")


@pytest.mark.django_db
def test_otp_locks_after_configured_failed_attempts(mocker, settings):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 2
    settings.OTP_VERIFICATION_LOCK_SECONDS = 60
    mocker.patch("apps.users.services.signup_otp_service.send_otp_sms_task.delay")
    mocker.patch.object(SendOTPService, "_generate_otp_code", return_value="123456")
    SendOTPService.send_signup_otp("09123456789")
    for _ in range(2):
        with pytest.raises(Exception):
            SendOTPService.verify_signup_otp("09123456789", "000000")
    with pytest.raises(Exception, match="Too many"):
        SendOTPService.verify_signup_otp("09123456789", "123456")


def test_security_cache_failure_blocks_otp_verification(mocker):
    guard = OTPVerificationGuard("signup", "09123456789")
    mocker.patch.object(guard.cache, "get", side_effect=OSError("cache unavailable"))

    with pytest.raises(SecurityCacheUnavailable):
        guard.verify("123456")


@pytest.mark.django_db
def test_password_login_failures_lock_temporarily_and_success_clears_counter(settings):
    settings.PASSWORD_LOGIN_MAX_ATTEMPTS = 2
    settings.PASSWORD_LOGIN_LOCK_SECONDS = 60
    user = CustomUser.objects.create_user(
        username="lockable_user",
        password="StrongPass123!",
    )

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(user.username, "wrong-password")
    assert LoginOtpService.login_with_username_password(
        user.username, "StrongPass123!"
    )["tokens"]

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(user.username, "wrong-password")
    assert LoginOtpService.login_with_username_password(
        user.username, "StrongPass123!"
    )["tokens"]

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(user.username, "wrong-password")
    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(user.username, "wrong-password")
    with pytest.raises(Throttled):
        LoginOtpService.login_with_username_password(user.username, "wrong-password")


@pytest.mark.django_db
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
    with pytest.raises(Throttled):
        LoginOtpService.login_with_username_password(
            first_user.username,
            "wrong-password",
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


@pytest.mark.django_db
def test_password_login_success_clears_only_matching_username_ip_counter(settings):
    settings.PASSWORD_LOGIN_MAX_ATTEMPTS = 2
    settings.PASSWORD_LOGIN_LOCK_SECONDS = 60
    first_user = CustomUser.objects.create_user(
        username="clear_first_user",
        password="StrongPass123!",
    )
    second_user = CustomUser.objects.create_user(
        username="clear_second_user",
        password="OtherStrongPass123!",
    )
    client_ip = "203.0.113.15"

    for user in (first_user, second_user):
        with pytest.raises(AuthenticationFailed):
            LoginOtpService.login_with_username_password(
                user.username,
                "wrong-password",
                client_ip=client_ip,
            )

    assert LoginOtpService.login_with_username_password(
        first_user.username,
        "StrongPass123!",
        client_ip=client_ip,
    )["tokens"]

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(
            second_user.username,
            "wrong-password",
            client_ip=client_ip,
        )
    with pytest.raises(Throttled):
        LoginOtpService.login_with_username_password(
            second_user.username,
            "wrong-password",
            client_ip=client_ip,
        )

    with pytest.raises(AuthenticationFailed):
        LoginOtpService.login_with_username_password(
            first_user.username,
            "wrong-password",
            client_ip=client_ip,
        )


@pytest.mark.django_db
def test_protected_profile_rejects_anonymous_and_public_login_is_explicit():
    client = APIClient()
    assert client.patch(reverse("users:update_profile"), {}, format="json").status_code == status.HTTP_401_UNAUTHORIZED
    # Invalid credentials are correctly a 401; this confirms the existing login contract.
    assert client.post(reverse("users:login_password"), {"username": "x", "password": "x"}, format="json").status_code == status.HTTP_401_UNAUTHORIZED
