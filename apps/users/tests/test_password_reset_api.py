import pytest
from django.core.cache import caches
from django.urls import reverse
from rest_framework import status

from apps.users.services.pass_reset_service import PasswordResetService
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestPasswordResetAPI:
    send_reset_otp_url = reverse("users:password_reset_send_otp")
    verify_and_reset_url = reverse("users:password_reset_verify_and_reset")

    def test_reset_otp_request_does_not_enumerate_accounts(self, api_client, mocker):
        existing_phone = "09123456789"
        unknown_phone = "09123456788"
        UserFactory(phone_number=existing_phone)
        mocker.patch.object(
            PasswordResetService,
            "_generate_otp_code",
            return_value="123456",
        )
        delivery = mocker.patch(
            "apps.users.services.pass_reset_service.send_otp_sms_task.delay"
        )

        existing_response = api_client.post(
            self.send_reset_otp_url,
            {"phone_number": existing_phone},
            format="json",
        )
        unknown_response = api_client.post(
            self.send_reset_otp_url,
            {"phone_number": unknown_phone},
            format="json",
        )

        assert existing_response.status_code == status.HTTP_200_OK
        assert unknown_response.status_code == status.HTTP_200_OK
        assert existing_response.data == unknown_response.data == {
            "message": "password reset otp code successfully sent.",
            "expires_in": 120,
        }
        assert delivery.call_args_list == [mocker.call(existing_phone, "123456")]
        assert caches["security"].get(
            PasswordResetService._guard(existing_phone).code_key
        ) == "123456"
        assert (
            caches["security"].get(
                PasswordResetService._guard(unknown_phone).code_key
            )
            is None
        )

    def test_reset_otp_request_rejects_invalid_phone_format(self, api_client):
        response = api_client.post(
            self.send_reset_otp_url,
            {"phone_number": "invalid-phone"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_password_reset_uses_real_service_and_consumes_otp(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        user = UserFactory(phone_number=phone_number)
        user.set_password("OldStrongPass123!")
        user.save(update_fields=["password"])
        mocker.patch.object(
            PasswordResetService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.pass_reset_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_reset_otp_url,
            {"phone_number": phone_number},
            format="json",
        )
        payload = {
            "phone_number": phone_number,
            "otp": "123456",
            "password": "NewStrongPass1!",
        }

        first_response = api_client.post(
            self.verify_and_reset_url,
            payload,
            format="json",
        )
        replay_response = api_client.post(
            self.verify_and_reset_url,
            payload,
            format="json",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert first_response.data["message"] == "password changed successfully."
        assert set(first_response.data["tokens"]) == {"access", "refresh"}
        user.refresh_from_db()
        assert user.check_password("NewStrongPass1!")
        assert replay_response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(replay_response.data["otp"]) == (
            "Invalid or expired verification code."
        )

    def test_password_reset_rejects_wrong_otp_generically(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        UserFactory(phone_number=phone_number)
        mocker.patch.object(
            PasswordResetService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.pass_reset_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_reset_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        response = api_client.post(
            self.verify_and_reset_url,
            {
                "phone_number": phone_number,
                "otp": "999999",
                "password": "NewStrongPass1!",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."

    def test_password_reset_verification_rejects_invalid_phone_format(
        self,
        api_client,
    ):
        response = api_client.post(
            self.verify_and_reset_url,
            {
                "phone_number": "invalid-phone",
                "otp": "123456",
                "password": "NewStrongPass1!",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    @pytest.mark.parametrize(
        "password",
        ["weak", "VeryLongStrongPass123!@"],
    )
    def test_password_reset_rejects_invalid_password(self, api_client, password):
        response = api_client.post(
            self.verify_and_reset_url,
            {
                "phone_number": "09123456789",
                "otp": "123456",
                "password": password,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_password_reset_does_not_disclose_inactive_account_state(
        self,
        api_client,
        mocker,
    ):
        phone_number = "09123456789"
        UserFactory(phone_number=phone_number, is_active=False)
        mocker.patch.object(
            PasswordResetService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.pass_reset_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_reset_otp_url,
            {"phone_number": phone_number},
            format="json",
        )

        response = api_client.post(
            self.verify_and_reset_url,
            {
                "phone_number": phone_number,
                "otp": "123456",
                "password": "NewStrongPass1!",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."

