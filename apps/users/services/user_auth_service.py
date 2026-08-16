from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError
from apps.lib.loggers import AppLogger
from ..models import CustomUser, Address
from ..jwt import revoke_user_refresh_tokens
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from secrets import compare_digest

class UserAuthService:

    @classmethod
    def complete_user_profile(cls, user: CustomUser, validated_data: dict) -> CustomUser:
        # This service is also used directly in tests and management code.  Keep
        # onboarding unable to accidentally persist a raw password even when a
        # caller bypasses the request serializer.
        if "password" in validated_data:
            raise ValidationError({
                "credentials": "Use profile update to change credentials.",
            })
        address_data = validated_data.pop('address')

        try:
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=user.pk)
                if not user.phone_number:
                    raise ValidationError({
                        "phone_number": "Verify a phone number before completing your profile.",
                    })
                if Address.objects.select_for_update().filter(user=user).exists():
                    raise ValidationError({
                        "address": "Use profile update to edit an existing address.",
                    })
                for attr, value in validated_data.items():
                    setattr(user, attr, value)

                user.save()

                Address.objects.create(
                    user=user,
                    title=address_data['title'],
                    full_address=address_data['full_address'],
                    postal_code=address_data.get('postal_code')
                )
        except IntegrityError as exc:
            raise ValidationError({
                "non_field_errors": ["Unable to update the profile with the provided information."],
            }) from exc

        AppLogger.log_activity(
            msg="profile.onboarding_completed",
            user=user,
            status="INFO"
        )
        return user

    @classmethod
    def update_user_profile(cls, user: CustomUser, validated_data: dict) -> CustomUser:
        password = validated_data.pop('password', None)
        address_data = validated_data.pop('address', None)

        try:
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=user.pk)
                if password:
                    user.set_password(password)
                    revoke_user_refresh_tokens(user)

                for attr, value in validated_data.items():
                    setattr(user, attr, value)

                user.save()

                if address_data is not None:
                    address_id = address_data.pop('id', None)
                    if address_id is None:
                        missing_fields = {
                            field: "This field is required."
                            for field in ("title", "full_address")
                            if field not in address_data
                        }
                        if missing_fields:
                            raise ValidationError({"address": missing_fields})
                        if Address.objects.select_for_update().filter(user=user).exists():
                            raise ValidationError({
                                "address": "An address ID is required to update an existing address.",
                            })
                        address = Address(user=user)
                    else:
                        address = Address.objects.select_for_update().filter(
                            pk=address_id,
                            user=user,
                        ).first()
                        if address is None:
                            raise ValidationError({
                                "address": "Address not found.",
                            })

                    for field in ("title", "full_address", "postal_code"):
                        if field in address_data:
                            setattr(address, field, address_data[field])
                    address.save()
        except IntegrityError as exc:
            raise ValidationError({
                "non_field_errors": ["Unable to update the profile with the provided information."],
            }) from exc

        AppLogger.log_activity(
            msg="profile.updated",
            user=user,
            status="INFO"
        )
        return user

    @classmethod
    @transaction.atomic
    def logout_user(cls, user: CustomUser, refresh_token: str) -> None:
        try:
            token = RefreshToken(refresh_token)
            token_user_id = str(token.get(api_settings.USER_ID_CLAIM, ""))
            if not compare_digest(token_user_id, str(user.pk)):
                raise TokenError("Token does not belong to the authenticated user.")
            token.blacklist()

            AppLogger.log_activity(
                msg="User logged out successfully and token blacklisted.",
                status="INFO"
            )
        except TokenError:
            AppLogger.log_security(msg="Logout rejected an invalid refresh token.", user=user)
            raise ValidationError({
                "refresh": "token is invalid or expired."
            })
