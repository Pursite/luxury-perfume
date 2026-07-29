import pytest
from django.urls import reverse
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.tests.factories import UserFactory


@pytest.fixture
def api_client():
    """Fixture to provide a Django REST Framework APIClient instance."""
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache_before_and_after():
    """Clear Redis cache before and after each test case to ensure test isolation."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestSigninFlow:
    # API endpoints for signin flow
    LOGIN_USER_PASS_URL = reverse('users:login_password')
    SEND_LOGIN_OTP_URL = reverse('users:login_send_otp')
    VERIFY_LOGIN_OTP_URL = reverse('users:verify_login_otp')

    def test_login_user_pass_success(self, api_client, mocker):
        """Success path: Valid credentials for a complete profile user returns 200 OK and tokens."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.login_with_username_password',
            return_value={
                "message": "successfully logged in.",
                "tokens": {"access": "fake-access-token", "refresh": "fake-refresh-token"}
            }
        )

        payload = {
            "username": "complete_user",
            "password": "SecurePass123!"
        }
        response = api_client.post(self.LOGIN_USER_PASS_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "successfully logged in."
        assert "tokens" in response.data
        assert response.data["tokens"]["access"] == "fake-access-token"

    def test_login_user_pass_invalid_credentials(self, api_client, mocker):
        """Failure path: Invalid credentials or incomplete profile raises AuthenticationFailed."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.login_with_username_password',
            side_effect=AuthenticationFailed("Invalid username or password.")
        )

        payload = {
            "username": "incomplete_or_wrong_user",
            "password": "WrongPassword!"
        }
        response = api_client.post(self.LOGIN_USER_PASS_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_send_login_otp_success(self, api_client, mocker):
        """Success path: Registered phone number returns 200 OK and success message."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.send_login_otp',
            return_value={
                "message": "otp code successfully sent.",
                "expires_in": 120
            }
        )

        payload = {"phone_number": "09123456789"}
        response = api_client.post(self.SEND_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "otp code successfully sent."
        assert response.data["expires_in"] == 120

    def test_send_login_otp_user_not_found(self, api_client, mocker):
        """Failure path: Requesting OTP for a phone number that doesn't exist returns 400 Bad Request."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.send_login_otp',
            side_effect=ValidationError({"phone_number": "no user found with this phone number."})
        )

        payload = {"phone_number": "09110000000"}
        response = api_client.post(self.SEND_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_send_login_otp_invalid_phone_format(self, api_client):
        """Failure path: Serializer validation fails for badly formatted phone number."""
        payload = {"phone_number": "not-a-phone-number"}
        response = api_client.post(self.SEND_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_verify_login_otp_success(self, api_client, mocker):
        """Success path: Valid OTP for active user returns 200 OK and tokens."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.verify_login_otp',
            return_value={
                "message": "successfully logged in.",
                "tokens": {"access": "fake-access-token", "refresh": "fake-refresh-token"}
            }
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "123456"
        }
        response = api_client.post(self.VERIFY_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "successfully logged in."
        assert "tokens" in response.data

    def test_verify_login_otp_expired_or_none(self, api_client, mocker):
        """Failure path: Expired or unrequested OTP returns 400 Bad Request."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.verify_login_otp',
            side_effect=ValidationError({"otp": "otp code expired or there is no request."})
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "123456"
        }
        response = api_client.post(self.VERIFY_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data

    def test_verify_login_otp_wrong_code(self, api_client, mocker):
        """Failure path: Entering an incorrect OTP digits returns 400 Bad Request."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.verify_login_otp',
            side_effect=ValidationError({"otp": "invalid otp."})
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "999999"
        }
        response = api_client.post(self.VERIFY_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data

    def test_verify_login_otp_deactivated_account(self, api_client, mocker):
        """Failure path: Authenticating an inactive user (`is_active=False`) returns 401 Unauthorized."""
        mocker.patch(
            'apps.users.services.login_otp_service.LoginOtpService.verify_login_otp',
            side_effect=AuthenticationFailed("your account is deactivated.")
        )

        payload = {
            "phone_number": "09121112233",
            "otp": "123456"
        }
        response = api_client.post(self.VERIFY_LOGIN_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


    LOGOUT_URL = reverse('users:logout')


    def test_logout_success(self, api_client):
        """Success path: Valid refresh token blacklists the token and logs out."""
        user = UserFactory()
        api_client.force_authenticate(user=user)

        refresh_token = RefreshToken.for_user(user)

        payload = {
            "refresh": str(refresh_token)
        }

        response = api_client.post(self.LOGOUT_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "successfully logged out."


    def test_logout_invalid_or_blacklisted_token(self, api_client):
        """Failure path: Sending a fake or invalid refresh token returns 400 Bad Request."""
        user = UserFactory()
        api_client.force_authenticate(user=user)

        payload = {
            "refresh": "fake-and-invalid-refresh-token"
        }

        response = api_client.post(self.LOGOUT_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "refresh" in response.data


    def test_logout_unauthenticated_user(self, api_client):
        """Failure path: Unauthenticated user cannot access the logout endpoint returns 401."""
        payload = {
            "refresh": "some-token"
        }

        response = api_client.post(self.LOGOUT_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
