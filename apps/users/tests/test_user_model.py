import pytest

from apps.users.models import CustomUser


@pytest.mark.django_db
class TestCustomUserManager:
    def test_create_user_requires_phone_number(self):
        with pytest.raises(ValueError, match="Phone number is required"):
            CustomUser.objects.create_user(phone_number="")

    def test_create_superuser_requires_password(self):
        with pytest.raises(ValueError, match="Superuser must have a password"):
            CustomUser.objects.create_superuser(phone_number="09123456789")

    def test_create_superuser_requires_staff_flag(self):
        with pytest.raises(ValueError, match="is_staff=True"):
            CustomUser.objects.create_superuser(
                phone_number="09123456789",
                password="StrongPass123!",
                is_staff=False,
            )

    def test_create_superuser_requires_superuser_flag(self):
        with pytest.raises(ValueError, match="is_superuser=True"):
            CustomUser.objects.create_superuser(
                phone_number="09123456789",
                password="StrongPass123!",
                is_superuser=False,
            )
