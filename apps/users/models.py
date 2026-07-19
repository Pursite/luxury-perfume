from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.validators import RegexValidator
from apps.lib.basemodel import BaseModel


class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, **extra_fields):
        if not phone_number:
            raise ValueError("Ph")

        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        user = self.create_user(phone_number, **extra_fields)
        if password:
            user.set_password(password)
            user.save(using=self._db)
        return user


class CustomUser(AbstractBaseUser, PermissionsMixin, BaseModel):
    phone_regex = RegexValidator(
        regex=r'^09\d{9}$',
        message="Phone number must be entered in the format: '0912345678'."
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=11, unique=True)

    username = models.CharField(max_length=150, unique=True, null=True, blank=True)

    email = models.EmailField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username if self.username else self.phone_number

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
        identifier = self.user.username if self.user.username else self.user.phone_number
        return f"{identifier} - {self.title}"

