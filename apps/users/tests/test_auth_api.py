import time

import pytest
from django.core.cache import caches
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.services.login_otp_service import LoginOtpService
from apps.users.jwt import REFRESH_TOKEN_COOKIE_NAME, REFRESH_TOKEN_COOKIE_PATH
from apps.users.selectors import UserSelector
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestAuthenticationAPI:
    password_login_url = reverse("users:login_password")
    send_login_otp_url = reverse("users:login_send_otp")
    verify_login_otp_url = reverse("users:verify_login_otp")
    logout_url = reverse("users:logout")

    def test_password_login_returns_real_tokens_for_valid_credentials(self, api_client):
        user = UserFactory(username="password_user")
        user.set_password("SecurePass123!")
        user.save(update_fields=["password"])

        response = api_client.post(
            self.password_login_url,
            {"username": "PASSWORD_USER", "password": "SecurePass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "successfully logged in."
        assert set(response.data["tokens"]) == {"access"}
        cookie = response.cookies[REFRESH_TOKEN_COOKIE_NAME]
        assert cookie["httponly"]
        assert cookie["path"] == REFRESH_TOKEN_COOKIE_PATH
        assert cookie["domain"] == ""
        assert cookie["samesite"].lower() == "lax"
        assert "no-store" in response["Cache-Control"]

    @override_settings(REFRESH_TOKEN_COOKIE_SECURE=True)
    def test_refresh_cookie_secure_flag_and_token_expiry_are_aligned(self, api_client):
        user = UserFactory(username="secure_cookie_user")
        user.set_password("SecurePass123!")
        user.save(update_fields=["password"])

        response = api_client.post(
            self.password_login_url,
            {"username": "secure_cookie_user", "password": "SecurePass123!"},
            format="json",
        )

        cookie = response.cookies[REFRESH_TOKEN_COOKIE_NAME]
        refresh = RefreshToken(cookie.value)
        assert cookie["secure"]
        expected_max_age = max(0, int(refresh["exp"]) - int(time.time()))
        assert abs(int(cookie["max-age"]) - expected_max_age) <= 1
        assert cookie["expires"]

    def test_password_login_throttle_fails_closed_when_security_cache_is_unavailable(
        self,
        api_client,
        mocker,
    ):
        user = UserFactory(username="password_user")
        user.set_password("SecurePass123!")
        user.save(update_fields=["password"])
        mocker.patch.object(
            caches["security"],
            "get",
            side_effect=OSError("cache unavailable"),
        )

        response = api_client.post(
            self.password_login_url,
            {"username": "password_user", "password": "SecurePass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "temporarily unavailable" in str(response.data["detail"])

    @pytest.mark.parametrize(
        ("username", "password"),
        [
            ("unknown_user", "WrongPassword!"),
            ("password_user", "WrongPassword!"),
        ],
    )
    def test_password_login_uses_generic_invalid_credentials_response(
        self,
        api_client,
        username,
        password,
    ):
        user = UserFactory(username="password_user")
        user.set_password("SecurePass123!")
        user.save(update_fields=["password"])

        response = api_client.post(
            self.password_login_url,
            {"username": username, "password": password},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert str(response.data["detail"]) == "Username or password is incorrect."

    def test_login_otp_request_does_not_enumerate_accounts(self, api_client, mocker):
        existing_phone = "09123456789"
        unknown_phone = "09123456788"
        UserFactory(phone_number=existing_phone)
        mocker.patch.object(
            LoginOtpService,
            "_generate_otp_code",
            return_value="123456",
        )
        delivery = mocker.patch(
            "apps.users.services.login_otp_service.send_otp_sms_task.delay"
        )

        existing_response = api_client.post(
            self.send_login_otp_url,
            {"phone_number": existing_phone},
            format="json",
            REMOTE_ADDR="198.51.100.10",
        )
        unknown_response = api_client.post(
            self.send_login_otp_url,
            {"phone_number": unknown_phone},
            format="json",
            REMOTE_ADDR="198.51.100.11",
        )

        assert existing_response.status_code == status.HTTP_200_OK
        assert unknown_response.status_code == status.HTTP_200_OK
        assert existing_response.data == unknown_response.data == {
            "message": "otp code successfully sent.",
            "expires_in": 120,
        }
        assert delivery.call_args_list == [mocker.call(existing_phone, "123456")]
        assert caches["security"].get(
            LoginOtpService._guard(existing_phone).code_key
        ) == "123456"
        assert (
            caches["security"].get(LoginOtpService._guard(unknown_phone).code_key)
            is None
        )

    def test_login_otp_request_rejects_invalid_phone_format(self, api_client):
        response = api_client.post(
            self.send_login_otp_url,
            {"phone_number": "invalid"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["phone_number"] == [
            "Phone number must be entered in the format: '09123456789'."
        ]

    def test_login_otp_verification_uses_real_service_and_consumes_code(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        UserFactory(phone_number=phone_number)
        mocker.patch.object(
            LoginOtpService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.login_otp_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_login_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        first_response = api_client.post(
            self.verify_login_otp_url,
            {"phone_number": phone_number, "otp": "123456"},
            format="json",
        )
        replay_response = api_client.post(
            self.verify_login_otp_url,
            {"phone_number": phone_number, "otp": "123456"},
            format="json",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert first_response.data["message"] == "successfully logged in."
        assert set(first_response.data["tokens"]) == {"access"}
        assert REFRESH_TOKEN_COOKIE_NAME in first_response.cookies
        assert replay_response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(replay_response.data["otp"]) == (
            "Invalid or expired verification code."
        )

    def test_login_otp_verification_rejects_unrequested_code_generically(
        self,
        api_client,
    ):
        response = api_client.post(
            self.verify_login_otp_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."

    def test_login_otp_verification_does_not_disclose_inactive_state(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        UserFactory(phone_number=phone_number, is_active=False)
        mocker.patch.object(
            LoginOtpService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.login_otp_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_login_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        response = api_client.post(
            self.verify_login_otp_url,
            {"phone_number": phone_number, "otp": "123456"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."

    def test_logout_blacklists_refresh_and_rejects_reuse(self, api_client):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        refresh_value = str(refresh)
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = refresh_value

        first_response = api_client.post(
            self.logout_url,
            format="json",
            HTTP_ORIGIN="http://testserver",
        )
        second_response = api_client.post(
            self.logout_url,
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
        assert second_response.status_code == status.HTTP_200_OK
        assert second_response.cookies[REFRESH_TOKEN_COOKIE_NAME]["max-age"] == 0

    def test_logout_rejects_invalid_token(self, api_client):
        UserFactory()
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = "fake-and-invalid-refresh-token"

        response = api_client.post(
            self.logout_url,
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies[REFRESH_TOKEN_COOKIE_NAME]["path"] == REFRESH_TOKEN_COOKIE_PATH

    def test_refresh_rotates_and_blacklists_the_superseded_refresh_token(self, api_client):
        user = UserFactory()
        original_refresh = str(RefreshToken.for_user(user))
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = original_refresh

        response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = original_refresh
        replay_response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"access"}
        assert response.cookies[REFRESH_TOKEN_COOKIE_NAME]["path"] == REFRESH_TOKEN_COOKIE_PATH
        assert "no-store" in response["Cache-Control"]
        assert replay_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_is_not_blocked_by_the_global_anonymous_throttle(
        self,
        api_client,
    ):
        user = UserFactory()
        refresh = str(RefreshToken.for_user(user))
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = refresh
        caches["default"].set(
            "throttle_anon_198.51.100.30",
            [time.time()] * 100,
            timeout=86400,
        )

        response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            REMOTE_ADDR="198.51.100.30",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"access"}

    def test_refresh_keeps_its_own_rate_limit(self, api_client):
        user = UserFactory()
        first_refresh = str(RefreshToken.for_user(user))
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = first_refresh
        caches["security"].set(
            "throttle_token_refresh_198.51.100.31",
            [time.time()] * 29,
            timeout=60,
        )

        first_response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            REMOTE_ADDR="198.51.100.31",
            HTTP_ORIGIN="http://testserver",
        )
        second_response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            REMOTE_ADDR="198.51.100.31",
            HTTP_ORIGIN="http://testserver",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_refresh_rejects_tokens_issued_before_a_password_change(self, api_client):
        user = UserFactory()
        stale_refresh = str(RefreshToken.for_user(user))
        user.set_password("ChangedPassword123!")
        user.save(update_fields=["password"])
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = stale_refresh

        response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_without_cookie_is_anonymous_and_deletes_scoped_cookie(self, api_client):
        response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        deleted = response.cookies[REFRESH_TOKEN_COOKIE_NAME]
        assert deleted["path"] == REFRESH_TOKEN_COOKIE_PATH
        assert deleted["domain"] == ""
        assert deleted["max-age"] == 0
        assert "no-store" in response["Cache-Control"]

    def test_logout_works_with_an_expired_access_token(self, api_client):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer expired-access-token")

        response = api_client.post(
            self.logout_url,
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert response.status_code == status.HTTP_200_OK
        assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
        assert response.cookies[REFRESH_TOKEN_COOKIE_NAME]["path"] == REFRESH_TOKEN_COOKIE_PATH

    def test_nonexistent_password_login_performs_a_dummy_password_hash(self, mocker):
        password_check = mocker.patch(
            "apps.users.selectors.check_password",
            return_value=False,
        )

        with pytest.raises(
            AuthenticationFailed,
            match="Username or password is incorrect",
        ):
            UserSelector.authenticate_by_username_password(
                username="missing_customer",
                password="WrongPassword123!",
            )

        password_check.assert_called_once()

    @pytest.mark.parametrize(
        ("url_name", "is_verification", "phone_limit", "ip_limit"),
        [
            ("users:signup_send_otp", False, 1, 10),
            ("users:login_send_otp", False, 1, 10),
            ("users:password_reset_send_otp", False, 1, 10),
            ("users:signup_verify_otp", True, 10, 10),
            ("users:verify_login_otp", True, 10, 10),
            ("users:password_reset_verify_and_reset", True, 10, 10),
        ],
    )
    @pytest.mark.parametrize("dimension", ["phone", "ip"])
    def test_every_otp_endpoint_enforces_phone_and_ip_rate_limits(
        self,
        api_client,
        settings,
        url_name,
        is_verification,
        phone_limit,
        ip_limit,
        dimension,
    ):
        settings.OTP_VERIFICATION_MAX_ATTEMPTS = 100
        url = reverse(url_name)
        limit = phone_limit if dimension == "phone" else ip_limit

        def payload(index):
            data = {"phone_number": f"0912{index:07d}"}
            if is_verification:
                data.update({"otp": "000000", "password": "LongEnoughPassword123!"})
            return data

        for index in range(limit):
            request_payload = payload(5000000 if dimension == "phone" else 5000000 + index)
            remote_addr = (
                f"198.51.100.{index + 1}"
                if dimension == "phone"
                else "198.51.100.200"
            )
            response = api_client.post(
                url,
                request_payload,
                format="json",
                REMOTE_ADDR=remote_addr,
            )
            assert response.status_code in {
                status.HTTP_200_OK,
                status.HTTP_201_CREATED,
                status.HTTP_400_BAD_REQUEST,
            }

        exhausted_response = api_client.post(
            url,
            payload(5000000 if dimension == "phone" else 5999999),
            format="json",
            REMOTE_ADDR=("198.51.100.250" if dimension == "phone" else "198.51.100.200"),
        )

        assert exhausted_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_logout_requires_a_trusted_origin(self, api_client):
        response = api_client.post(
            self.logout_url,
            format="json",
            HTTP_ORIGIN="https://attacker.example",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
