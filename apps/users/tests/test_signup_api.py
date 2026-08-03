import pytest
from django.urls import reverse
from django.db import IntegrityError
from rest_framework import status

from apps.lib.throttle import SignupRateThrottle
from apps.users.models import CustomUser
from apps.users.tests.factories import UserFactory

@pytest.fixture
def signup_payload():
    return {
        "username": "secure_customer",
        "password": "CorrectHorseBatteryStaple42!",
    }


@pytest.mark.django_db
class TestUserSignupAPIView:
    url = reverse("apps.users:signup")

    def test_signup_creates_hashed_password_and_returns_safe_response(
        self,
        api_client,
        signup_payload,
    ):
        response = api_client.post(self.url, signup_payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"] == {"username": "secure_customer"}
        assert set(response.data["tokens"]) == {"access", "refresh"}
        user = CustomUser.objects.get(username="secure_customer")
        assert user.check_password(signup_payload["password"])
        assert user.password != signup_payload["password"]
        assert user.phone_number is None
        assert user.email is None
        assert "password" not in response.data["user"]
        assert "phone_number" not in response.data["user"]
        assert "email" not in response.data["user"]

    def test_new_signup_can_immediately_use_password_login(
        self,
        api_client,
        signup_payload,
    ):
        response = api_client.post(self.url, signup_payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        login_response = api_client.post(
            reverse("apps.users:login_password"),
            {
                "username": signup_payload["username"],
                "password": signup_payload["password"],
            },
            format="json",
        )

        assert login_response.status_code == status.HTTP_200_OK
        assert set(login_response.data["tokens"]) == {"access", "refresh"}

    def test_duplicate_username_returns_generic_non_enumerating_error(
        self,
        api_client,
        signup_payload,
    ):
        UserFactory(username="secure_customer")

        response = api_client.post(self.url, signup_payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.data) == {"non_field_errors"}
        assert "Unable to create an account" in str(response.data["non_field_errors"])
        assert "username" not in response.data
        assert "email" not in response.data

    def test_case_variant_of_legacy_username_returns_generic_conflict(
        self,
        api_client,
        signup_payload,
    ):
        user = UserFactory(username="legacy_customer")
        CustomUser.objects.filter(pk=user.pk).update(username="Legacy_Customer")

        response = api_client.post(
            self.url,
            {**signup_payload, "username": "LEGACY_CUSTOMER"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.data) == {"non_field_errors"}

    def test_weak_password_is_rejected_by_django_password_validators(
        self,
        api_client,
        signup_payload,
    ):
        response = api_client.post(
            self.url,
            {**signup_payload, "password": "password"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        assert not CustomUser.objects.filter(username="secure_customer").exists()

    def test_unique_constraint_race_returns_same_generic_error(
        self,
        api_client,
        mocker,
        signup_payload,
    ):
        mocker.patch(
            "apps.users.services.signup_service.CustomUser.objects.create_user",
            side_effect=IntegrityError("simulated unique constraint race"),
        )

        response = api_client.post(self.url, signup_payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.data) == {"non_field_errors"}
        assert "Unable to create an account" in str(response.data["non_field_errors"])

    def test_signup_is_strictly_rate_limited(
        self,
        api_client,
        monkeypatch,
        signup_payload,
    ):
        monkeypatch.setattr(
            SignupRateThrottle,
            "THROTTLE_RATES",
            {**SignupRateThrottle.THROTTLE_RATES, "signup": "1/min"},
        )

        first_response = api_client.post(self.url, signup_payload, format="json")
        second_response = api_client.post(
            self.url,
            {**signup_payload, "username": "another_customer"},
            format="json",
        )

        assert first_response.status_code == status.HTTP_201_CREATED
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
