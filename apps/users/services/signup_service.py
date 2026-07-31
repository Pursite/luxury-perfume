from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.users.models import CustomUser


class SignupIdentityConflict(Exception):
    """Raised when a concurrent signup conflicts with a unique identifier."""


@transaction.atomic
def create_user_service(*, data: dict[str, Any]) -> CustomUser:
    """Create an active password user without exposing uniqueness race details."""
    try:
        user = CustomUser.objects.create_user(
            username=data["username"],
            password=data["password"],
        )
    except (DjangoValidationError, IntegrityError) as exc:
        raise SignupIdentityConflict from exc
    return user
