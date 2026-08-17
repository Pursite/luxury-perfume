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
def test_signup_and_profile_password_inputs_use_django_similarity_validation():
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
    update = UserProfileUpdateInputSerializer(
        data={"password": password},
        context={"request": request},
        partial=True,
    )

    assert signup.is_valid() is False
    assert update.is_valid() is False
    assert "password" in signup.errors
    assert "password" in update.errors


@pytest.mark.django_db
def test_password_reset_serializer_only_applies_account_independent_validation():
    user = UserFactory(
        username="reset_customer",
        email="resetidentity@example.com",
        phone_number="09123456789",
    )
    serializer = PasswordResetVerifyInputSerializer(
        data={
            "phone_number": user.phone_number,
            "otp": "123456",
            "password": "resetidentity@example.com123!",
        },
    )

    assert serializer.is_valid() is True


@pytest.mark.django_db
def test_profile_serializers_accept_the_canonical_150_character_username():
    user = UserFactory(username="current_user")
    request = APIRequestFactory().patch("/")
    request.user = user
    username = "u" * 150

    complete = CompleteProfileInputSerializer(
        data={
            "username": username,
            "email": "complete@example.com",
            "first_name": "Complete",
            "last_name": "Customer",
            "address": {"title": "Home", "full_address": "Test address"},
        },
        context={"request": request},
    )
    update = UserProfileUpdateInputSerializer(
        data={"username": username},
        context={"request": request},
        partial=True,
    )

    assert complete.is_valid() is True
    assert update.is_valid() is True


@pytest.mark.django_db
def test_profile_serializers_reject_case_insensitive_username_conflicts():
    UserFactory(username="Existing_User", email="existing@example.com")
    current_user = UserFactory(username="current_user")
    request = APIRequestFactory().patch("/")
    request.user = current_user

    complete = CompleteProfileInputSerializer(
        data={
            "username": "existing_user",
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
