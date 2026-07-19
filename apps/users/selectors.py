from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser


class UserSelector:

    @staticmethod
    def check_user_exists_by_phone(phone_number: str) -> bool:
        return CustomUser.objects.filter(phone_number=phone_number).exists()

    @staticmethod
    def get_user_by_phone(phone_number: str) -> CustomUser:
        try:
            return CustomUser.objects.get(phone_number=phone_number)
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
        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            raise AuthenticationFailed("Username or password is incorrect")

        if not user.is_active:
            raise AuthenticationFailed("Your account is inactive")

        if not user.is_profile_complete:
            raise AuthenticationFailed(
                "You account is not complete, please complete your account."
            )

        if not user.check_password(password):
            raise AuthenticationFailed("Username or password is incorrect")

        if not user.has_usable_password():
            raise AuthenticationFailed("No usable password defined for this user, please complete your account.")

        return user

    @staticmethod
    def is_username_taken(username: str, exclude_user_id: int = None) -> bool:
        query = CustomUser.objects.all()
        if exclude_user_id:
            query = query.exclude(pk=exclude_user_id)
        return query.filter(username=username).exists()

    @staticmethod
    def is_email_taken(email: str, exclude_user_id: int = None) -> bool:
        query = CustomUser.objects.all()
        if exclude_user_id:
            query = query.exclude(pk=exclude_user_id)
        return query.filter(email=email).exists()
