from django.db import transaction
from rest_framework.exceptions import ValidationError
from apps.lib.loggers import AppLogger
from ..models import CustomUser, Address
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

class UserAuthService:

    @classmethod
    def complete_user_profile(cls, user: CustomUser, validated_data: dict) -> CustomUser:
        address_data = validated_data.pop('address')
        password = validated_data.pop('password')

        try:
            with transaction.atomic():
                for attr, value in validated_data.items():
                    setattr(user, attr, value)

                user.set_password(password)

                user.is_active = True
                user.save()

                Address.objects.create(
                    user=user,
                    title=address_data['title'],
                    full_address=address_data['full_address'],
                    postal_code=address_data.get('postal_code')
                )

            AppLogger.log_activity(
                msg=f"User {user.phone_number} successfully completed profile and added first address.",
                user=user,
                status="INFO"
            )
            return user

        except Exception as e:
            AppLogger.log_system_error(
                msg=f"Failed to complete profile for user {user.id}: {str(e)}",
                include_traceback=True
            )
            raise ValidationError({
                "non_field_errors": ["unknown error."]
            })

    @classmethod
    def update_user_profile(cls, user: CustomUser, validated_data: dict) -> CustomUser:
        password = validated_data.pop('password', None)

        try:
            with transaction.atomic():
                if password:
                    user.set_password(password)

                for attr, value in validated_data.items():
                    setattr(user, attr, value)

                user.save()

            AppLogger.log_activity(
                msg=f"User {user.phone_number} successfully updated their profile info.",
                user=user,
                status="INFO"
            )
            return user

        except Exception as e:
            AppLogger.log_system_error(
                msg=f"Failed to update profile for user {user.id}: {str(e)}",
                include_traceback=True
            )
            raise ValidationError({
                "non_field_errors": ["unknown error."]
            })

    @classmethod
    def logout_user(cls, refresh_token: str) -> None:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            AppLogger.log_activity(
                msg="User logged out successfully and token blacklisted.",
                status="INFO"
            )
        except TokenError as e:
            AppLogger.log_system_error(
                msg=f"Logout failed, invalid or expired token: {str(e)}"
            )
            raise ValidationError({
                "refresh": "token is invalid or expired."
            })
