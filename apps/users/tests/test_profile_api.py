import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.tests.factories import UserFactory
from apps.users.jwt import REFRESH_TOKEN_COOKIE_NAME
from apps.users.models import Address


@pytest.mark.django_db
class TestProfileFlow:
    CURRENT_PROFILE_URL = "/api/v1/users/profile/"
    COMPLETE_PROFILE_URL = reverse('users:complete_profile')
    UPDATE_PROFILE_URL = reverse('users:update_profile')

    def test_current_profile_requires_authentication(self, api_client):
        response = api_client.get(self.CURRENT_PROFILE_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_current_profile_returns_only_the_authenticated_users_safe_fields(
        self,
        api_client,
    ):
        user = UserFactory(
            username="current_customer",
            email="current@example.com",
            first_name="Current",
            last_name="Customer",
            is_staff=True,
            is_superuser=True,
        )
        first_address = Address.objects.create(
            user=user,
            title="Home",
            full_address="First address",
            postal_code="1234567890",
        )
        second_address = Address.objects.create(
            user=user,
            title="Office",
            full_address="Second address",
            postal_code=None,
        )
        other_user = UserFactory(username="other_customer")
        Address.objects.create(
            user=other_user,
            title="Other home",
            full_address="Must not be returned",
        )
        api_client.force_authenticate(user=user)

        response = api_client.get(self.CURRENT_PROFILE_URL)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"data"}
        assert set(response.data["data"]) == {
            "id",
            "phone_number",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_profile_complete",
            "addresses",
        }
        assert response.data["data"]["id"] == str(user.pk)
        assert response.data["data"]["username"] == "current_customer"
        assert [address["id"] for address in response.data["data"]["addresses"]] == [
            str(first_address.pk),
            str(second_address.pk),
        ]
        assert all(
            set(address) == {"id", "title", "full_address", "postal_code"}
            for address in response.data["data"]["addresses"]
        )
        serialized = repr(response.data).lower()
        for unsafe_field in (
            "password",
            "token",
            "refresh",
            "is_staff",
            "is_superuser",
            "permissions",
            "groups",
        ):
            assert unsafe_field not in serialized

    def test_current_profile_uses_two_queries_for_user_and_addresses(
        self,
        api_client,
        django_assert_num_queries,
    ):
        user = UserFactory()
        Address.objects.create(user=user, title="Home", full_address="Address")
        api_client.force_authenticate(user=user)

        with django_assert_num_queries(2):
            response = api_client.get(self.CURRENT_PROFILE_URL)

        assert response.status_code == status.HTTP_200_OK

    def test_complete_profile_success_does_not_change_password_or_account_status(self, api_client):
        """Onboarding fills customer data without changing credentials or activation."""
        user = UserFactory(username=None, email=None, first_name="", last_name="")
        user.set_password("OriginalPassword123!")
        user.save(update_fields=["password"])
        api_client.force_authenticate(user=user)

        payload = {
            "username": "my_user_123",
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
        assert user.check_password("OriginalPassword123!") is True
        assert Address.objects.filter(user=user).count() == 1
        assert user.is_profile_complete is True

    def test_complete_profile_unauthenticated(self, api_client):
        """Failure path: Unauthenticated user gets 401."""
        response = api_client.post(self.COMPLETE_PROFILE_URL, data={}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_complete_profile_requires_a_verified_phone_number(self, api_client):
        user = UserFactory(phone_number=None, email=None, first_name="", last_name="")
        api_client.force_authenticate(user=user)

        payload = {
            "username": "my_user_123",
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
        assert "phone_number" in response.data

    def test_complete_profile_duplicate_username_or_email(self, api_client):
        """Failure path: Taking an existing username or email returns 400."""
        UserFactory(username="taken_user", email="taken@example.com")

        user = UserFactory()
        api_client.force_authenticate(user=user)

        payload = {
            "username": "taken_user",
            "email": "taken@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "address": {"title": "خانه", "full_address": "تهران"}
        }

        response = api_client.post(self.COMPLETE_PROFILE_URL, data=payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "username" in response.data
        assert "email" in response.data

    def test_complete_profile_cannot_create_a_second_onboarding_address(self, api_client):
        user = UserFactory(email=None, first_name="", last_name="")
        Address.objects.create(user=user, title="Home", full_address="Existing address")
        api_client.force_authenticate(user=user)

        response = api_client.post(
            self.COMPLETE_PROFILE_URL,
            {
                "username": user.username,
                "email": "profile@example.com",
                "first_name": "Profile",
                "last_name": "Customer",
                "address": {"title": "Home", "full_address": "New address"},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Address.objects.filter(user=user).count() == 1


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

    def test_update_profile_rejects_password_similar_to_new_email_without_persisting(
        self,
        api_client,
    ):
        user = UserFactory(
            username="profile_customer",
            email="previous@example.com",
            first_name="Profile",
            last_name="Customer",
        )
        user.set_password("OldStrongPass123!")
        user.save(update_fields=["password"])
        api_client.force_authenticate(user=user)

        response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {
                "email": "nextidentity@example.com",
                "password": "nextidentity@example.com123!",
            },
            format="json",
        )

        user.refresh_from_db()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        assert user.email == "previous@example.com"
        assert user.check_password("OldStrongPass123!")

    def test_update_profile_reuses_an_owned_address_without_creating_a_duplicate(
        self,
        api_client,
    ):
        user = UserFactory()
        address = Address.objects.create(
            user=user,
            title="Home",
            full_address="Old address",
        )
        api_client.force_authenticate(user=user)

        response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {
                "email": "updated@example.com",
                "address": {
                    "id": str(address.pk),
                    "title": "Office",
                    "full_address": "New address",
                    "postal_code": "1234567890",
                },
            },
            format="json",
        )

        address.refresh_from_db()
        user.refresh_from_db()
        assert response.status_code == status.HTTP_200_OK
        assert user.email == "updated@example.com"
        assert Address.objects.filter(user=user).count() == 1
        assert address.title == "Office"
        assert address.full_address == "New address"

    def test_update_profile_partially_updates_an_owned_address(self, api_client):
        user = UserFactory()
        address = Address.objects.create(
            user=user,
            title="Home",
            full_address="Old address",
            postal_code="1111111111",
        )
        api_client.force_authenticate(user=user)

        response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {
                "address": {
                    "id": str(address.pk),
                    "full_address": "Updated address",
                },
            },
            format="json",
        )

        address.refresh_from_db()
        assert response.status_code == status.HTTP_200_OK
        assert address.title == "Home"
        assert address.full_address == "Updated address"
        assert address.postal_code == "1111111111"

    def test_update_profile_rejects_an_address_owned_by_another_user(self, api_client):
        user = UserFactory()
        other_address = Address.objects.create(
            user=UserFactory(),
            title="Other home",
            full_address="Other address",
        )
        api_client.force_authenticate(user=user)

        response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {
                "address": {
                    "id": str(other_address.pk),
                    "title": "Attempted update",
                    "full_address": "Attempted address",
                },
            },
            format="json",
        )

        other_address.refresh_from_db()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert other_address.title == "Other home"

    def test_normal_profile_edits_do_not_invalidate_existing_tokens(self, api_client):
        user = UserFactory()
        user.set_password("OriginalPassword123!")
        user.save(update_fields=["password"])
        refresh = RefreshToken.for_user(user)
        stale_access = str(refresh.access_token)
        api_client.force_authenticate(user=user)

        update_response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {"first_name": "Updated"},
            format="json",
        )
        api_client.force_authenticate(user=None)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {stale_access}")
        token_response = api_client.patch(
            self.UPDATE_PROFILE_URL,
            {"last_name": "StillAuthorized"},
            format="json",
        )
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
        refresh_response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert update_response.status_code == status.HTTP_200_OK
        assert token_response.status_code == status.HTTP_200_OK
        assert refresh_response.status_code == status.HTTP_200_OK

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
        api_client.cookies[REFRESH_TOKEN_COOKIE_NAME] = str(refresh)
        refresh_response = api_client.post(
            reverse("users:token_refresh"),
            format="json",
            HTTP_ORIGIN="http://testserver",
        )

        assert password_update.status_code == status.HTTP_200_OK
        assert stale_access_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
