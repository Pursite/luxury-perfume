from rest_framework.exceptions import AuthenticationFailed
from typing import Optional

from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser


class UserSelector:

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
    def generate_tokens_for_user(user: CustomUser) -> dict:
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    @staticmethod
    def authenticate_by_username_password(username: str, password: str) -> CustomUser:
        """Authenticate without disclosing account existence or account state."""
        generic_error = "Username or password is incorrect."
        username = CustomUser.normalize_username(username)
        users = list(
            CustomUser.objects.filter(username__iexact=username).order_by("pk")[:2]
        )
        if len(users) != 1:
            raise AuthenticationFailed(generic_error)
        user = users[0]

        if not user.has_usable_password() or not user.check_password(password):
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
    def is_username_taken(username: str, exclude_user_id: int = None) -> bool:
        query = CustomUser.objects.all()
        if exclude_user_id:
            query = query.exclude(pk=exclude_user_id)
        return query.filter(
            username__iexact=CustomUser.normalize_username(username),
        ).exists()

    @staticmethod
    def is_email_taken(email: str, exclude_user_id: int = None) -> bool:
        query = CustomUser.objects.all()
        if exclude_user_id:
            query = query.exclude(pk=exclude_user_id)
        return query.filter(email=email).exists()
