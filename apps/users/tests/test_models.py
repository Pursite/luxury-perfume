import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.users.models import CustomUser


@pytest.mark.django_db
class TestCustomUserManager:
    def test_create_user_requires_at_least_one_identity_for_active_accounts(self):
        with pytest.raises(ValueError, match="username or phone number"):
            CustomUser.objects.create_user()

    def test_inactive_user_can_exist_without_an_identity(self):
        user = CustomUser.objects.create_user(is_active=False)

        user.full_clean()
        assert user.is_active is False
        assert user.has_identity is False

    def test_create_user_supports_username_only_phone_only_and_both_identities(self):
        username_user = CustomUser.objects.create_user(
            username="  USERNAME_USER  ",
            password="StrongPass123!",
        )
        phone_user = CustomUser.objects.create_user(phone_number=" 09123456789 ")
        both_user = CustomUser.objects.create_user(
            username="Both_User",
            phone_number="09123456788",
        )

        assert username_user.username == "USERNAME_USER"
        assert username_user.phone_number is None
        assert username_user.check_password("StrongPass123!")
        assert phone_user.phone_number == "09123456789"
        assert phone_user.has_usable_password() is False
        assert both_user.username == "Both_User"
        assert both_user.phone_number == "09123456788"

    def test_create_user_runs_model_validation_for_invalid_phone_numbers(self):
        with pytest.raises(DjangoValidationError, match="Phone number must be entered"):
            CustomUser.objects.create_user(phone_number="not-a-phone-number")

    @pytest.mark.parametrize("phone_number", ["۰۹۱۲۳۴۵۶۷۸۹", "0912345678۹"])
    def test_phone_numbers_reject_non_ascii_digits(self, phone_number):
        with pytest.raises(DjangoValidationError, match="Phone number must be entered"):
            CustomUser.objects.create_user(phone_number=phone_number)

    def test_create_user_runs_model_validation_for_invalid_model_fields(self):
        with pytest.raises(DjangoValidationError, match="Enter a valid email address"):
            CustomUser.objects.create_user(
                username="valid_username",
                email="not-an-email",
                password="StrongPass123!",
            )

    def test_user_string_has_a_safe_fallback_without_an_identity(self):
        assert str(CustomUser(pk=123)) == "123"

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


@pytest.mark.django_db
def test_case_insensitive_username_and_email_constraints_are_enforced_by_database():
    CustomUser.objects.create(
        username="CaseSensitiveUser",
        email="CaseSensitive@example.com",
        password="!",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomUser.objects.create(
                username="casesensitiveuser",
                email="other@example.com",
                password="!",
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomUser.objects.create(
                username="other_user",
                email="casesensitive@example.com",
                password="!",
            )


@pytest.mark.django_db(transaction=True)
def test_identity_constraint_migration_deactivates_legacy_active_identityless_users():
    old_target = [("users", "0003_alter_customuser_phone_number")]
    new_target = [("users", "0004_customuser_users_active_user_requires_identity")]

    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    LegacyCustomUser = old_apps.get_model("users", "CustomUser")
    user = LegacyCustomUser.objects.create(
        password="!",
        is_active=True,
        username=None,
        phone_number=None,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    MigratedCustomUser = new_apps.get_model("users", "CustomUser")

    assert MigratedCustomUser.objects.get(pk=user.pk).is_active is False


@pytest.mark.django_db(transaction=True)
def test_case_insensitive_identity_migration_refuses_legacy_conflicts_without_rewriting_them():
    old_target = [("users", "0004_customuser_users_active_user_requires_identity")]
    new_target = [("users", "0005_customuser_case_insensitive_identities")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    LegacyCustomUser = old_apps.get_model("users", "CustomUser")
    first = LegacyCustomUser.objects.create(
        username="LegacyUser",
        email="legacy-one@example.com",
        password="!",
        is_active=True,
    )
    second = LegacyCustomUser.objects.create(
        username="legacyuser",
        email="legacy-two@example.com",
        password="!",
        is_active=True,
    )

    try:
        with pytest.raises(RuntimeError, match="case-insensitive identity conflicts"):
            executor.migrate(new_target)

        assert LegacyCustomUser.objects.filter(pk__in=[first.pk, second.pk]).count() == 2
    finally:
        LegacyCustomUser.objects.filter(pk__in=[first.pk, second.pk]).delete()
        executor.migrate(new_target)
