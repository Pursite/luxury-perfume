import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from apps.users.tests.factories import UserFactory
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestPasswordResetFlow:
    SEND_RESET_OTP_URL = reverse('users:password_reset_send_otp')
    VERIFY_AND_RESET_URL = reverse('users:password_reset_verify_and_reset')

    def test_send_reset_otp_success(self, api_client, mocker):
        """Success path: Existing user requests OTP, returns 200 OK."""
        mocker.patch(
            'apps.users.services.pass_reset_service.PasswordResetService.send_reset_otp',
            return_value={"message": "password reset otp code successfully sent.", "expires_in": 120}
        )

        UserFactory(phone_number="09123456789")

        payload = {"phone_number": "09123456789"}
        response = api_client.post(self.SEND_RESET_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "password reset otp code successfully sent."

    def test_send_reset_otp_user_not_found(self, api_client, mocker):
        """Failure path: Requesting OTP for a phone number that doesn't exist returns 400."""
        mocker.patch(
            'apps.users.services.pass_reset_service.PasswordResetService.send_reset_otp',
            side_effect=ValidationError({"phone_number": "no user found with this phone number."})
        )

        payload = {"phone_number": "09110000000"}
        response = api_client.post(self.SEND_RESET_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_send_reset_otp_invalid_phone_format(self, api_client):
        """Failure path: Serializer validation fails for badly formatted phone number."""
        payload = {"phone_number": "invalid-phone"}
        response = api_client.post(self.SEND_RESET_OTP_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_verify_and_reset_password_invalid_phone_format(self, api_client):
        """Failure path: Password reset verification validates phone number format before service calls."""
        payload = {
            "phone_number": "invalid-phone",
            "otp": "123456",
            "password": "NewStrongPass123!@"
        }

        response = api_client.post(self.VERIFY_AND_RESET_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_verify_and_reset_password_success(self, api_client, mocker):
        """Success path: Valid OTP and strong password returns 200 OK and new tokens."""
        mocker.patch(
            'apps.users.services.pass_reset_service.PasswordResetService.verify_and_reset_password',
            return_value={
                "message": "password changed successfully.",
                "tokens": {"access": "new-access-token", "refresh": "new-refresh-token"}
            }
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "123456",
            "password": "NewStrongPass123!@"
        }
        response = api_client.post(self.VERIFY_AND_RESET_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "password changed successfully."
        assert "tokens" in response.data

    def test_verify_and_reset_password_wrong_otp(self, api_client, mocker):
        """Failure path: Entering an incorrect or expired OTP returns 400 Bad Request."""
        mocker.patch(
            'apps.users.services.pass_reset_service.PasswordResetService.verify_and_reset_password',
            side_effect=ValidationError({"otp": "invalid otp."})
        )

        payload = {
            "phone_number": "09123456789",
            "otp": "999999",
            "password": "NewStrongPass123!@"
        }
        response = api_client.post(self.VERIFY_AND_RESET_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data

    def test_verify_and_reset_password_weak_password(self, api_client):
        """Failure path: Weak password fails serializer complexity validation without mocking."""
        payload = {
            "phone_number": "09123456789",
            "otp": "123456",
            "password": "weak"
        }
        response = api_client.post(self.VERIFY_AND_RESET_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_verify_and_reset_password_too_long_password(self, api_client):
        """Failure path: Password reset keeps profile password length policy consistent."""
        payload = {
            "phone_number": "09123456789",
            "otp": "123456",
            "password": "VeryLongStrongPass123!@"
        }

        response = api_client.post(self.VERIFY_AND_RESET_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
