from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError


def validate_password_policy(password, user=None):
    """Apply the configured Django password policy to a candidate user."""
    try:
        password_validation.validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from exc
