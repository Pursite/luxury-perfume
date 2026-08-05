import pytest
from rest_framework.test import APIRequestFactory

from apps.users.serializers import (
    CompleteProfileInputSerializer,
    PasswordResetVerifyInputSerializer,
    UserSignupInputSerializer,
    UserProfileUpdateInputSerializer,
)
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_every_password_entry_point_uses_django_similarity_validation():
    current_user = UserFactory(
        username="current_user",
        phone_number="09123456789",
    )
    request = APIRequestFactory().patch("/")
    request.user = current_user
    password = "current_user_123!"

    signup = UserSignupInputSerializer(
        data={"username": "new_signup_user", "password": "new_signup_user_123!"}
    )
    complete = CompleteProfileInputSerializer(
        data={
            "username": "current_user",
            "password": password,
            "email": "current@example.com",
            "first_name": "Current",
            "last_name": "User",
            "address": {"title": "Home", "full_address": "Test address"},
        },
        context={"request": request},
    )
    update = UserProfileUpdateInputSerializer(
        data={"password": password},
        context={"request": request},
        partial=True,
    )
    reset = PasswordResetVerifyInputSerializer(
        data={
            "phone_number": current_user.phone_number,
            "otp": "123456",
            "password": password,
        },
    )

    assert signup.is_valid() is False
    assert complete.is_valid() is False
    assert update.is_valid() is False
    assert reset.is_valid() is False
    assert "password" in signup.errors
    assert "password" in complete.errors
    assert "password" in update.errors
    assert "password" in reset.errors


@pytest.mark.django_db
def test_profile_serializers_reject_case_insensitive_username_conflicts():
    UserFactory(username="Existing_User", email="existing@example.com")
    current_user = UserFactory(username="current_user")
    request = APIRequestFactory().patch("/")
    request.user = current_user

    complete = CompleteProfileInputSerializer(
        data={
            "username": "existing_user",
            "password": "StrongPass1!",
            "email": "new@example.com",
            "first_name": "Test",
            "last_name": "User",
            "address": {"title": "Home", "full_address": "Test address"},
        },
        context={"request": request},
    )
    update = UserProfileUpdateInputSerializer(
        data={"username": "EXISTING_USER"},
        context={"request": request},
        partial=True,
    )

    assert complete.is_valid() is False
    assert "username" in complete.errors
    assert update.is_valid() is False
    assert "username" in update.errors
