import pytest
from django.core.cache import caches
from django.urls import reverse
from rest_framework import status

from apps.users.services.profile_phone_service import ProfilePhoneVerificationService
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestProfilePhoneVerificationAPI:
    send_url = reverse("users:profile_phone_send_otp")
    verify_url = reverse("users:profile_phone_verify_otp")

    def test_phone_is_persisted_only_after_successful_authenticated_verification(
        self,
        api_client,
        mocker,
    ):
        user = UserFactory(phone_number=None)
        api_client.force_authenticate(user=user)
        mocker.patch.object(
            ProfilePhoneVerificationService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )

        send_response = api_client.post(
            self.send_url,
            {"phone_number": "09123456789"},
            format="json",
        )
        user.refresh_from_db()

        assert send_response.status_code == status.HTTP_200_OK
        assert user.phone_number is None

        failed_response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "000000"},
            format="json",
        )
        user.refresh_from_db()

        assert failed_response.status_code == status.HTTP_400_BAD_REQUEST
        assert user.phone_number is None

        verified_response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )
        user.refresh_from_db()

        assert verified_response.status_code == status.HTTP_200_OK
        assert user.phone_number == "09123456789"

    def test_phone_verification_rejects_another_accounts_owned_phone(
        self,
        api_client,
        mocker,
    ):
        owner = UserFactory(phone_number="09123456789")
        claimant = UserFactory(phone_number=None)
        api_client.force_authenticate(user=claimant)
        delivery = mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )

        response = api_client.post(
            self.send_url,
            {"phone_number": owner.phone_number},
            format="json",
        )

        claimant.refresh_from_db()
        assert response.status_code == status.HTTP_200_OK
        assert claimant.phone_number is None
        delivery.assert_not_called()

    def test_phone_verification_cannot_replace_an_existing_verified_phone(
        self,
        api_client,
        mocker,
    ):
        user = UserFactory(phone_number="09123456789")
        replacement_phone = "09123456788"
        api_client.force_authenticate(user=user)
        delivery = mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )

        send_response = api_client.post(
            self.send_url,
            {"phone_number": replacement_phone},
            format="json",
        )
        ProfilePhoneVerificationService._guard(user, replacement_phone).store_code("123456")
        verify_response = api_client.post(
            self.verify_url,
            {"phone_number": replacement_phone, "otp": "123456"},
            format="json",
        )

        user.refresh_from_db()
        assert send_response.status_code == status.HTTP_200_OK
        delivery.assert_not_called()
        assert verify_response.status_code == status.HTTP_400_BAD_REQUEST
        assert user.phone_number == "09123456789"

    def test_phone_verification_rejects_a_ownership_race_after_otp_consumption(
        self,
        api_client,
        mocker,
    ):
        claimant = UserFactory(phone_number=None)
        api_client.force_authenticate(user=claimant)
        mocker.patch.object(
            ProfilePhoneVerificationService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_url,
            {"phone_number": "09123456789"},
            format="json",
        )
        UserFactory(phone_number="09123456789")

        response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )

        claimant.refresh_from_db()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["otp"]) == "Invalid or expired verification code."
        assert claimant.phone_number is None

    def test_phone_verification_code_cannot_be_consumed_by_another_user(
        self,
        api_client,
        mocker,
    ):
        requester = UserFactory(phone_number=None)
        other_user = UserFactory(phone_number=None)
        mocker.patch.object(
            ProfilePhoneVerificationService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )
        api_client.force_authenticate(user=requester)
        api_client.post(
            self.send_url,
            {"phone_number": "09123456789"},
            format="json",
        )
        api_client.force_authenticate(user=other_user)

        response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )

        requester.refresh_from_db()
        other_user.refresh_from_db()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert requester.phone_number is None
        assert other_user.phone_number is None

    def test_phone_verification_code_is_single_use(self, api_client, mocker):
        user = UserFactory(phone_number=None)
        api_client.force_authenticate(user=user)
        mocker.patch.object(
            ProfilePhoneVerificationService,
            "_generate_otp_code",
            return_value="123456",
        )
        mocker.patch(
            "apps.users.services.profile_phone_service.send_otp_sms_task.delay"
        )
        api_client.post(
            self.send_url,
            {"phone_number": "09123456789"},
            format="json",
        )

        first_response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )
        second_response = api_client.post(
            self.verify_url,
            {"phone_number": "09123456789", "otp": "123456"},
            format="json",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_400_BAD_REQUEST

    def test_phone_verification_throttle_fails_closed_when_security_cache_is_unavailable(
        self,
        api_client,
        mocker,
    ):
        user = UserFactory(phone_number=None)
        api_client.force_authenticate(user=user)
        mocker.patch.object(
            caches["security"],
            "get",
            side_effect=OSError("cache unavailable"),
        )

        response = api_client.post(
            self.send_url,
            {"phone_number": "09123456789"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        user.refresh_from_db()
        assert user.phone_number is None
