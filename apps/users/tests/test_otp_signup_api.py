import pytest
from django.urls import reverse
from rest_framework import status

from apps.users.models import CustomUser
from apps.users.services.signup_otp_service import SendOTPService
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestSignupOTPAPI:
    send_otp_url = reverse("users:signup_send_otp")
    verify_otp_url = reverse("users:signup_verify_otp")

    def test_signup_otp_request_uses_real_service(self, api_client, mocker):
        phone_number = "09123456789"
        mocker.patch.object(
            SendOTPService,
            "_generate_otp_code",
            return_value="123456",
        )
        delivery = mocker.patch(
            "apps.users.services.signup_otp_service.send_otp_sms_task.delay"
        )

        response = api_client.post(
            self.send_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "message": "Verification code sent successfully.",
            "expires_in": 120,
        }
        delivery.assert_called_once_with(phone_number, "123456")

    def test_signup_otp_request_does_not_disclose_existing_account(
        self,
        api_client,
        mocker,
    ):
        existing_phone = "09129998877"
        UserFactory(phone_number=existing_phone)
        delivery = mocker.patch(
            "apps.users.services.signup_otp_service.send_otp_sms_task.delay"
        )

        response = api_client.post(
            self.send_otp_url,
            {"phone_number": existing_phone},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "message": "Verification code sent successfully.",
            "expires_in": 120,
        }
        delivery.assert_not_called()

    def test_signup_otp_request_rejects_invalid_phone_format(self, api_client):
        response = api_client.post(
            self.send_otp_url,
            {"phone_number": "0912345"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_signup_otp_request_is_throttled_by_phone(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09121112233"
        mocker.patch(
            "apps.users.services.signup_otp_service.send_otp_sms_task.delay"
        )

        first_response = api_client.post(
            self.send_otp_url,
            {"phone_number": phone_number},
            format="json",
        )
        second_response = api_client.post(
            self.send_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_signup_otp_verification_creates_user_and_consumes_code(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        mocker.patch.object(
            SendOTPService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.signup_otp_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        first_response = api_client.post(
            self.verify_otp_url,
            {"phone_number": phone_number, "otp": "123456"},
            format="json",
        )
        replay_response = api_client.post(
            self.verify_otp_url,
            {"phone_number": phone_number, "otp": "123456"},
            format="json",
        )

        assert first_response.status_code == status.HTTP_201_CREATED
        assert first_response.data["message"] == "signup confirmed."
        assert set(first_response.data["tokens"]) == {"access", "refresh"}
        user = CustomUser.objects.get(phone_number=phone_number)
        assert user.has_usable_password() is False
        assert replay_response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(replay_response.data["otp"]) == (
            "Invalid or expired verification code."
        )

    def test_signup_otp_verification_rejects_invalid_length(self, api_client):
        response = api_client.post(
            self.verify_otp_url,
            {"phone_number": "09123456789", "otp": "1234"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "otp" in response.data

    def test_signup_otp_verification_rejects_wrong_code(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        mocker.patch.object(
            SendOTPService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.signup_otp_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        response = api_client.post(
            self.verify_otp_url,
            {"phone_number": phone_number, "otp": "999999"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."

