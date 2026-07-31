from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from apps.lib.basemodel import BaseModel


class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number=None, password=None, **extra_fields):
        user = self.model(phone_number=phone_number, **extra_fields)
        user.normalize_identities()

        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        try:
            user.full_clean()
        except DjangoValidationError as exc:
            identity_error = "An active user must have a username or phone number."
            if identity_error in exc.message_dict.get("__all__", []):
                raise ValueError(identity_error) from exc
            raise
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if not password:
            raise ValueError("Superuser must have a password.")

        return self.create_user(phone_number, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin, BaseModel):
    phone_regex = RegexValidator(
        regex=r'^09\d{9}$',
        message="Phone number must be entered in the format: '0912345678'."
    )
    phone_number = models.CharField(
        validators=[phone_regex],
        max_length=11,
        unique=True,
        null=True,
        blank=True,
    )

    username = models.CharField(max_length=150, unique=True, null=True, blank=True)

    email = models.EmailField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | (models.Q(username__isnull=False) & ~models.Q(username=""))
                    | (models.Q(phone_number__isnull=False) & ~models.Q(phone_number=""))
                ),
                name="users_active_user_requires_identity",
            ),
        ]

    @staticmethod
    def normalize_username(value):
        if value is None:
            return None
        # Preserve stored casing for legacy and user-facing compatibility.  Lookup
        # and availability checks are deliberately case-insensitive instead.
        value = value.strip()
        return value or None

    @staticmethod
    def normalize_phone_number(value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    def normalize_identities(self):
        self.username = self.normalize_username(self.username)
        self.phone_number = self.normalize_phone_number(self.phone_number)

    @property
    def has_identity(self):
        return bool(self.username or self.phone_number)

    def clean(self):
        super().clean()
        self.normalize_identities()
        if self.is_active and not self.has_identity:
            from django.core.exceptions import ValidationError

            raise ValidationError({
                "__all__": "An active user must have a username or phone number.",
            })

    def save(self, *args, **kwargs):
        self.normalize_identities()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.username or self.phone_number or str(self.pk or "user")

    @property
    def is_profile_complete(self):
        has_basic_info = bool(self.username and self.email and self.first_name and self.last_name)
        has_address = self.addresses.exists()
        return has_basic_info and has_address


class Address(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='addresses')
    title = models.CharField(max_length=50, help_text="مثلاً: خانه، شرکت")
    full_address = models.TextField()
    postal_code = models.CharField(max_length=10, blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.title}"
