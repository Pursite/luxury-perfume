from typing import Optional
from uuid import UUID
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Prefetch
from django.utils.translation import gettext as _
from rest_framework.exceptions import AuthenticationFailed

from .models import Address, CustomUser


# This is deliberately not a usable credential. Hashing against it gives absent
# and ambiguous username paths comparable password-work to normal failures.
DUMMY_PASSWORD_HASH = make_password("not-a-user-password")


class UserSelector:

    @staticmethod
    def get_current_profile(*, user: CustomUser) -> CustomUser:
        return CustomUser.objects.prefetch_related(
            Prefetch(
                "addresses",
                queryset=Address.objects.order_by("created_at", "id"),
            )
        ).get(pk=user.pk)

    @staticmethod
    def check_user_exists_by_phone(phone_number: str) -> bool:
        return CustomUser.objects.filter(
            phone_number=CustomUser.normalize_phone_number(phone_number),
        ).exists()

    @staticmethod
    def get_user_by_phone(phone_number: str) -> Optional[CustomUser]:
        try:
            return CustomUser.objects.get(
                phone_number=CustomUser.normalize_phone_number(phone_number),
            )
        except CustomUser.DoesNotExist:
            return None

    @staticmethod
    def authenticate_by_username_password(username: str, password: str) -> CustomUser:
        """Authenticate without disclosing account existence or account state."""
        generic_error = _("Username or password is incorrect.")
        username = CustomUser.normalize_username(username)
        users = list(
            CustomUser.objects.filter(username__iexact=username).order_by("pk")[:2]
        )
        if len(users) != 1:
            check_password(password, DUMMY_PASSWORD_HASH)
            raise AuthenticationFailed(generic_error)
        user = users[0]

        if not user.has_usable_password():
            check_password(password, DUMMY_PASSWORD_HASH)
            raise AuthenticationFailed(generic_error)

        if not user.check_password(password):
            raise AuthenticationFailed(generic_error)

        if not user.is_active:
            raise AuthenticationFailed(generic_error)

        return user

    @staticmethod
    def signup_username_exists(*, username: str) -> bool:
        """Check username availability with a case-insensitive compatibility query."""
        return CustomUser.objects.filter(
            username__iexact=CustomUser.normalize_username(username),
        ).exists()

    @staticmethod
    def is_username_taken(
            username: str,
            exclude_user_id: UUID | None = None,
    ) -> bool:
        query = CustomUser.objects.all()

        if exclude_user_id is not None:
            query = query.exclude(pk=exclude_user_id)

        return query.filter(
            username__iexact=CustomUser.normalize_username(username),
        ).exists()

    @staticmethod
    def is_email_taken(
            email: str,
            exclude_user_id: UUID | None = None,
    ) -> bool:
        query = CustomUser.objects.all()

        if exclude_user_id is not None:
            query = query.exclude(pk=exclude_user_id)

        return query.filter(
            email__iexact=CustomUser.normalize_email(email),
        ).exists()
