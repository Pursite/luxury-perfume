import pytest
from django.urls import reverse
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from django.test import override_settings
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
class TestSignupOTPFlow:
    SEND_OTP_URL = reverse('users:signup_send_otp')
    VERIFY_OTP_URL = reverse('users:signup_verify_otp')

    def test_send_otp_success(self, api_client, mocker):
        """Success path: Valid phone number returns 200 OK and success message."""
        mocker.patch(
            'apps.users.services.signup_otp_service.SendOTPService.send_signup_otp',
            return_value={"message": "Verification code sent successfully."}
        )

        payload = {"phone_number": "09123456789"}
        response = api_client.post(self.SEND_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Verification code sent successfully."

    def test_send_otp_invalid_phone_format(self, api_client):
        """Failure path: Invalid phone number format returns 400 Bad Request."""
        payload = {"phone_number": "0912345"}  # Incomplete phone number
        response = api_client.post(self.SEND_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_send_otp_existing_phone_uses_the_same_generic_response(self, api_client):
        """Signup OTP requests must not disclose whether a phone already has an account."""
        existing_phone = "09129998877"
        UserFactory(phone_number=existing_phone)

        payload = {"phone_number": existing_phone}
        response = api_client.post(self.SEND_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Verification code sent successfully."

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_send_otp_throttling(self, api_client, mocker):
        """Throttle path: Consecutive requests within rate limit drop trigger 429 Too Many Requests."""
        mocker.patch(
            'apps.users.services.signup_otp_service.SendOTPService.send_signup_otp',
            return_value={"message": "Verification code sent successfully."}
        )

        payload = {"phone_number": "09121112233"}

        # First request: Allowed
        response1 = api_client.post(self.SEND_OTP_URL, data=payload, format='json')
        assert response1.status_code == status.HTTP_200_OK

        # Second immediate request: Blocked by throttle
        response2 = api_client.post(self.SEND_OTP_URL, data=payload, format='json')
        assert response2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_verify_otp_success(self, api_client, mocker):
        """Success path: Valid code registers user and returns tokens with 201 Created."""
        mocker.patch(
            'apps.users.services.signup_otp_service.SendOTPService.verify_signup_otp',
            return_value={"access": "fake-access-token", "refresh": "fake-refresh-token"}
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "123456"
        }
        response = api_client.post(self.VERIFY_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert "access" in response.data
        assert "refresh" in response.data

    def test_verify_otp_invalid_length(self, api_client):
        """Failure path: Providing an OTP with incorrect length returns 400 Bad Request."""
        payload = {
            "phone_number": "09123456789",
            "otp": "1234"  # Expected length is usually 6 or 4 digits
        }
        response = api_client.post(self.VERIFY_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data

    def test_verify_otp_wrong_code(self, api_client, mocker):
        """Failure path: Valid length but incorrect/expired OTP value returns 400 Bad Request."""
        mocker.patch(
            'apps.users.services.signup_otp_service.SendOTPService.verify_signup_otp',
            side_effect=ValidationError({"otp": "The code entered is incorrect or expired."})
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "999999"
        }
        response = api_client.post(self.VERIFY_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data
