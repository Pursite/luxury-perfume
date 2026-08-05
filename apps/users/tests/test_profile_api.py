import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.tests.factories import UserFactory
from apps.users.models import Address


@pytest.mark.django_db
class TestProfileFlow:
    COMPLETE_PROFILE_URL = reverse('users:complete_profile')
    UPDATE_PROFILE_URL = reverse('users:update_profile')

    def test_complete_profile_success(self, api_client):
        """Success path: Valid data completes profile, creates address, and activates user."""
        user = UserFactory(username=None, email=None, first_name="", last_name="")
        api_client.force_authenticate(user=user)

        payload = {
            "username": "my_user_123",
            "password": "StrongPass22/@",
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "address": {
                "title": "خانه",
                "full_address": "تهران، خیابان ولیعصر، پلاک ۱",
                "postal_code": "1234567890"
            }
        }

        response = api_client.post(self.COMPLETE_PROFILE_URL, data=payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data

        user.refresh_from_db()
        assert user.username == "my_user_123"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.check_password("StrongPass22/@") is True
        assert Address.objects.filter(user=user).count() == 1
        assert user.is_profile_complete is True

    def test_complete_profile_unauthenticated(self, api_client):
        """Failure path: Unauthenticated user gets 401."""
        response = api_client.post(self.COMPLETE_PROFILE_URL, data={}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_complete_profile_weak_password(self, api_client):
        """Failure path: Password missing special characters or digits raises 400."""
        user = UserFactory()
        api_client.force_authenticate(user=user)

        payload = {
            "username": "my_user_123",
            "password": "short",
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "address": {
                "title": "خانه",
                "full_address": "تهران"
            }
        }

        response = api_client.post(self.COMPLETE_PROFILE_URL, data=payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_complete_profile_duplicate_username_or_email(self, api_client):
        """Failure path: Taking an existing username or email returns 400."""
        UserFactory(username="taken_user", email="taken@example.com")

        user = UserFactory()
        api_client.force_authenticate(user=user)

        payload = {
            "username": "taken_user",
            "password": "StrongPassword123!@",
            "email": "taken@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "address": {"title": "خانه", "full_address": "تهران"}
        }

        response = api_client.post(self.COMPLETE_PROFILE_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "username" in response.data
        assert "email" in response.data


    def test_update_profile_partial_success(self, api_client):
        """Success path: Partially updating fields (e.g., only first_name)."""
        user = UserFactory(first_name="OldName", username="old_user")
        api_client.force_authenticate(user=user)

        payload = {
            "first_name": "NewName"
        }

        response = api_client.patch(self.UPDATE_PROFILE_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "NewName"
        assert user.username == "old_user"  # فیلدهای دیگر نباید تغییر کنند

    def test_update_profile_password(self, api_client):
        """Success path: Updating password successfully hashes the new password."""
        user = UserFactory()
        api_client.force_authenticate(user=user)

        payload = {
            "password": "NewStrongPass123!@"
        }

        response = api_client.patch(self.UPDATE_PROFILE_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("NewStrongPass123!@") is True

    def test_password_update_invalidates_existing_access_and_refresh_tokens(self, api_client):
        user = UserFactory()
        user.set_password("OriginalPassword123!")
        user.save(update_fields=["password"])
        refresh = RefreshToken.for_user(user)
        stale_access = str(refresh.access_token)
        api_client.force_authenticate(user=user)

        password_update = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {"password": "NewStrongPass123!@"},
            format="json",
        )
        api_client.force_authenticate(user=None)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {stale_access}")
        stale_access_response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {"first_name": "Rejected"},
            format="json",
        )
        refresh_response = api_client.post(
            reverse("users:token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )

        assert password_update.status_code == status.HTTP_200_OK
        assert stale_access_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
