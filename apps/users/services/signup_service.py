from typing import Any

from django.db import IntegrityError, transaction

from apps.users.models import CustomUser


class SignupIdentityConflict(Exception):
    """Raised when a concurrent signup conflicts with a unique identifier."""


@transaction.atomic
def create_user_service(*, data: dict[str, Any]) -> CustomUser:
    """Create an active password user without exposing uniqueness race details."""
    try:
        user = CustomUser(username=data["username"])
        user.set_password(data["password"])
        user.save()
    except IntegrityError as exc:
        raise SignupIdentityConflict from exc
    return user
