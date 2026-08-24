from collections.abc import Iterable

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.users.jwt import revoke_user_refresh_tokens
from apps.users.models import Address, CustomUser


@transaction.atomic
def change_user_password_service(
    *,
    user: CustomUser,
    raw_password: str | None,
) -> CustomUser:
    """Change password state while revoking every outstanding refresh token."""
    locked_user = CustomUser.objects.select_for_update().get(pk=user.pk)
    if raw_password is None:
        locked_user.set_unusable_password()
    else:
        locked_user.set_password(raw_password)
    revoke_user_refresh_tokens(locked_user)
    locked_user.save(update_fields=["password", "updated_at"])
    return locked_user


@transaction.atomic
def delete_users_service(
    *,
    user_ids: Iterable[int],
    allow_privileged: bool,
) -> int:
    """Delete locked users after enforcing the Admin privilege boundary."""
    requested_ids = sorted({user_id for user_id in user_ids if user_id})
    if not requested_ids:
        return 0

    locked_users = list(
        CustomUser.objects.select_for_update()
        .filter(pk__in=requested_ids)
        .order_by("pk")
    )
    if not allow_privileged and any(
        user.is_staff or user.is_superuser for user in locked_users
    ):
        raise PermissionDenied

    locked_user_ids = [user.pk for user in locked_users]
    if locked_user_ids:
        CustomUser.objects.filter(pk__in=locked_user_ids).delete()
    return len(locked_user_ids)


@transaction.atomic
def delete_addresses_service(
    *,
    address_ids: Iterable,
    allow_privileged: bool,
) -> int:
    """Delete locked addresses after checking their current owners."""
    requested_ids = sorted({address_id for address_id in address_ids if address_id})
    if not requested_ids:
        return 0

    owner_ids = set(
        Address.objects.filter(pk__in=requested_ids).values_list(
            "user_id",
            flat=True,
        )
    )
    locked_owners = {
        user.pk: user
        for user in CustomUser.objects.select_for_update()
        .filter(pk__in=owner_ids)
        .order_by("pk")
    }
    locked_addresses = list(
        Address.objects.select_for_update()
        .filter(pk__in=requested_ids)
        .order_by("pk")
    )
    if any(address.user_id not in locked_owners for address in locked_addresses):
        raise PermissionDenied
    if not allow_privileged and any(
        locked_owners[address.user_id].is_staff
        or locked_owners[address.user_id].is_superuser
        for address in locked_addresses
    ):
        raise PermissionDenied

    locked_address_ids = [address.pk for address in locked_addresses]
    if locked_address_ids:
        Address.objects.filter(pk__in=locked_address_ids).delete()
    return len(locked_address_ids)
