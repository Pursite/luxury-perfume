import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from apps.users.serializers import (
    CompleteProfileInputSerializer,
    UserProfileUpdateInputSerializer,
    validate_password_complexity,
)
from apps.users.tests.factories import UserFactory


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("123456!", "english letter"),
        ("NoDigits!", "digit"),
        ("NoSpecial123", "characters"),
    ],
)
def test_password_complexity_rejects_each_missing_character_class(password, message):
    with pytest.raises(serializers.ValidationError, match=message):
        validate_password_complexity(password)


def test_password_complexity_accepts_required_character_classes():
    assert validate_password_complexity("Valid123!") == "Valid123!"


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

