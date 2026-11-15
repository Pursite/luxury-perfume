import pytest
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.jwt import REFRESH_TOKEN_COOKIE_NAME
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db
CHANGE_URL = "/api/v1/users/password/change/"


@pytest.mark.parametrize(
    "current,expected", [("OldStrongPass123!", 200), ("incorrect", 400), (None, 400)]
)
def test_change_password_requires_current_password(api_client, current, expected):
    user = UserFactory()
    user.set_password("OldStrongPass123!")
    user.save()
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    payload = {"password": "NewStrongPass123!"}
    if current is not None:
        payload["current_password"] = current
    response = api_client.post(CHANGE_URL, payload, format="json")
    assert response.status_code == expected
    user.refresh_from_db()
    assert user.check_password(
        "NewStrongPass123!" if expected == 200 else "OldStrongPass123!"
    )
    if expected == 200:
        assert api_client.get(reverse("users:current_profile")).status_code == 401
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
        assert (
            api_client.post(reverse("users:token_refresh"), format="json").status_code
            == 401
        )


def test_profile_cannot_change_password(api_client):
    user = UserFactory()
    api_client.force_authenticate(user)
    response = api_client.patch(
        reverse("users:update_profile"), {"password": "NewStrongPass123!"}
    )
    assert response.status_code == 400


def test_change_password_requires_authentication(api_client):
    assert (
        api_client.post(CHANGE_URL, {"password": "NewStrongPass123!"}).status_code
        == 401
    )


@pytest.mark.parametrize("usable", [True, False])
def test_password_account_capabilities(api_client, usable):
    user = UserFactory()
    if usable:
        user.set_password("StrongPass123!")
    else:
        user.set_unusable_password()
    user.save()
    api_client.force_authenticate(user)
    data = api_client.get(reverse("users:current_profile")).data["data"]
    assert data["has_usable_password"] is usable
    assert data["sms_available"] is False


@pytest.mark.parametrize("password", ["weak", "", "user_identity123!"])
def test_password_policy_and_otp_only_restrictions(api_client, password):
    user = UserFactory(username="user_identity")
    user.set_password("OldStrongPass123!")
    user.save()
    api_client.force_authenticate(user)
    response = api_client.post(
        CHANGE_URL, {"current_password": "OldStrongPass123!", "password": password}
    )
    assert response.status_code == 400
    user.set_unusable_password()
    user.save()
    response = api_client.post(
        CHANGE_URL, {"current_password": "anything", "password": "NewStrongPass123!"}
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert not user.has_usable_password()


def test_sms_disabled_does_not_break_password_login_signup_or_change(
    api_client, settings
):
    settings.SMS_ENABLED = False
    response = api_client.post(
        reverse("users:signup"),
        {"username": "sms_disabled_user", "password": "StrongPass123!"},
    )
    assert response.status_code == 201
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['tokens']['access']}"
    )
    assert (
        api_client.post(
            CHANGE_URL,
            {"current_password": "StrongPass123!", "password": "NewStrongPass123!"},
        ).status_code
        == 200
    )
    api_client.credentials()
    assert (
        api_client.post(
            reverse("users:login_password"),
            {"username": "sms_disabled_user", "password": "NewStrongPass123!"},
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("signup_send_otp", {"phone_number": "09123456789"}),
        ("login_send_otp", {"phone_number": "09123456789"}),
        ("password_reset_send_otp", {"phone_number": "09123456789"}),
        ("verify_login_otp", {"phone_number": "09123456789", "otp": "123456"}),
        ("signup_verify_otp", {"phone_number": "09123456789", "otp": "123456"}),
        (
            "password_reset_verify_and_reset",
            {
                "phone_number": "09123456789",
                "otp": "123456",
                "password": "NewStrongPass123!",
            },
        ),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_sms_disabled_or_unconfigured_fails_closed(
    api_client, settings, endpoint, payload, enabled
):
    settings.SMS_ENABLED = enabled
    settings.SMS_PROVIDER = "unregistered-provider"
    response = api_client.post(reverse(f"users:{endpoint}"), payload)
    assert response.status_code == 503
    assert "123456" not in str(response.data)


def test_direct_profile_service_rejects_password():
    from rest_framework.exceptions import ValidationError
    from apps.users.services.user_auth_service import UserAuthService

    user = UserFactory()
    with pytest.raises(ValidationError):
        UserAuthService.update_user_profile(user, {"password": "NewStrongPass123!"})


@pytest.mark.usefixtures("operational_sms")
def test_initial_password_requires_fresh_scoped_otp_and_revokes_tokens(api_client):
    from apps.users.services.password_service import setup_guard

    user = UserFactory(phone_number="09123456789")
    user.set_unusable_password()
    user.save()
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    url = reverse("users:password_set_verify")
    payload = {"otp": "123456", "password": "NewStrongPass123!"}
    assert api_client.post(url, payload).status_code == 400
    setup_guard(user).store_code("123456")
    response = api_client.post(url, payload)
    assert response.status_code == 200
    assert api_client.get(reverse("users:current_profile")).status_code == 401
    api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
    assert (
        api_client.post(reverse("users:token_refresh"), format="json").status_code
        == 401
    )
    user.refresh_from_db()
    assert user.check_password(payload["password"])


@pytest.mark.usefixtures("operational_sms")
def test_reset_revokes_access_and_refresh_tokens(api_client):
    from apps.users.services.pass_reset_service import PasswordResetService

    user = UserFactory(phone_number="09123456789")
    user.set_password("OldStrongPass123!")
    user.save()
    refresh = RefreshToken.for_user(user)
    PasswordResetService._guard(user.phone_number).store_code("123456")
    response = api_client.post(
        reverse("users:password_reset_verify_and_reset"),
        {
            "phone_number": user.phone_number,
            "otp": "123456",
            "password": "NewStrongPass123!",
        },
    )
    assert response.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    assert api_client.get(reverse("users:current_profile")).status_code == 401
    api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
    assert (
        api_client.post(reverse("users:token_refresh"), format="json").status_code
        == 401
    )


def test_password_change_and_login_preserve_password_whitespace(api_client):
    user = UserFactory(username="space_password_user")
    user.set_password(" OldStrongPass123! ")
    user.save()
    api_client.force_authenticate(user)
    assert (
        api_client.post(
            CHANGE_URL,
            {
                "current_password": " OldStrongPass123! ",
                "password": " NewStrongPass123! ",
            },
        ).status_code
        == 200
    )
    api_client.force_authenticate(None)
    assert (
        api_client.post(
            reverse("users:login_password"),
            {"username": user.username, "password": " NewStrongPass123! "},
        ).status_code
        == 200
    )


@pytest.mark.usefixtures("operational_sms")
def test_otp_only_account_cannot_use_recovery_to_bypass_initial_setup(
    api_client, mocker
):
    from apps.users.services.pass_reset_service import PasswordResetService

    user = UserFactory(phone_number="09123456789")
    user.set_unusable_password()
    user.save()
    delivery = mocker.patch(
        "apps.users.services.pass_reset_service.send_otp_sms_task.delay"
    )
    response = api_client.post(
        reverse("users:password_reset_send_otp"), {"phone_number": user.phone_number}
    )
    assert response.status_code == 200
    delivery.assert_not_called()
    PasswordResetService._guard(user.phone_number).store_code("123456")
    assert (
        api_client.post(
            reverse("users:password_reset_verify_and_reset"),
            {
                "phone_number": user.phone_number,
                "otp": "123456",
                "password": "NewStrongPass123!",
            },
        ).status_code
        == 400
    )
    user.refresh_from_db()
    assert not user.has_usable_password()


@pytest.mark.parametrize("endpoint", ["password_set_send", "password_set_verify"])
def test_initial_setup_requires_authentication(api_client, endpoint):
    assert api_client.post(reverse(f"users:{endpoint}"), {}).status_code == 401


@pytest.mark.parametrize("cidrs", [(), ("invalid-cidr",)])
def test_proxy_trust_requires_valid_explicit_networks(settings, cidrs):
    from apps.users.checks import check_auth_proxy_settings

    settings.AUTH_TRUST_PROXY_HEADERS = True
    settings.AUTH_TRUSTED_PROXY_CIDRS = cidrs
    assert [error.id for error in check_auth_proxy_settings(None)] == ["users.E001"]


@pytest.mark.usefixtures("operational_sms")
def test_setup_send_binds_code_to_account_without_returning_it(
    api_client, mocker, django_capture_on_commit_callbacks
):
    from apps.users.services.password_service import setup_guard

    user = UserFactory(phone_number="09123456789")
    user.set_unusable_password()
    user.save()
    api_client.force_authenticate(user)
    delivery = mocker.patch(
        "apps.users.services.password_service.send_otp_sms_task.delay"
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(reverse("users:password_set_send"), {})
    assert response.status_code == 200
    assert set(response.data) == {"message", "expires_in"}
    guard = setup_guard(user)
    code = guard.cache.get(guard.code_key)["code"]
    delivery.assert_called_once_with(user.phone_number, code)
    assert code not in str(response.data)
    assert (
        api_client.post(
            reverse("users:password_set_verify"),
            {"otp": code, "password": "NewStrongPass123!"},
        ).status_code
        == 200
    )
    assert (
        api_client.post(
            reverse("users:password_set_verify"),
            {"otp": code, "password": "OtherStrongPass123!"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "profile_phone_send_otp",
        "profile_phone_verify_otp",
        "password_set_send",
        "password_set_verify",
    ],
)
def test_authenticated_sms_operations_are_unavailable_when_disabled(
    api_client, endpoint
):
    user = UserFactory()
    user.set_unusable_password()
    user.save()
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse(f"users:{endpoint}"),
        {
            "phone_number": "09123456789",
            "otp": "123456",
            "password": "NewStrongPass123!",
        },
    )
    assert response.status_code == 503


def test_forged_headers_cannot_evade_password_attempt_lockout(api_client, settings):
    settings.PASSWORD_LOGIN_MAX_ATTEMPTS = 2
    user = UserFactory(username="forged_header_user")
    user.set_password("OldStrongPass123!")
    user.save()
    for index in range(2):
        response = api_client.post(
            reverse("users:login_password"),
            {"username": user.username, "password": "wrong"},
            HTTP_X_FORWARDED_FOR=f"198.51.100.{index + 1}",
        )
        assert response.status_code == 401
    response = api_client.post(
        reverse("users:login_password"),
        {"username": user.username, "password": "OldStrongPass123!"},
        HTTP_X_FORWARDED_FOR="198.51.100.99",
    )
    assert response.status_code == 429
