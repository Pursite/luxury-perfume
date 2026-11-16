import secrets

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.lib.loggers import AppLogger
from apps.lib.security_cache import OTPVerificationGuard
from apps.users.models import CustomUser
from apps.users.tasks import send_otp_sms_task

from .sms_availability import ensure_sms_available


class ProfilePhoneVerificationService:
    """Attach a phone to an authenticated account only after OTP verification."""

    purpose = "profile-phone"
    generic_otp_error = {"otp": "Invalid or expired verification code."}

    @staticmethod
    def _generate_otp_code() -> str:
        return f"{secrets.randbelow(900000) + 100000:06d}"

    @classmethod
    def _guard(
        cls,
        user: CustomUser,
        phone_number: str,
    ) -> OTPVerificationGuard:
        return OTPVerificationGuard(
            f"{cls.purpose}:{user.pk}",
            CustomUser.normalize_phone_number(phone_number),
        )

    @staticmethod
    def _request_response() -> dict:
        from django.conf import settings

        return {
            "message": "Verification code sent successfully.",
            "expires_in": settings.OTP_EXPIRY_SECONDS,
        }

    @classmethod
    def send_phone_verification(
        cls,
        user: CustomUser,
        phone_number: str,
    ) -> dict:
        ensure_sms_available()
        phone_number = CustomUser.normalize_phone_number(phone_number)
        if user.phone_number:
            return cls._request_response()
        is_owned_by_another_user = CustomUser.objects.filter(
            phone_number=phone_number,
        ).exclude(pk=user.pk).exists()
        if user.phone_number == phone_number or is_owned_by_another_user:
            return cls._request_response()

        otp_code = cls._generate_otp_code()
        otp_code = cls._guard(user, phone_number).store_code(otp_code)
        transaction.on_commit(lambda: send_otp_sms_task.delay(phone_number, otp_code))

        AppLogger.log_activity(
            msg="profile_phone_verification.queued",
            user=user,
            status="INFO",
        )
        return cls._request_response()

    @classmethod
    def verify_phone_verification(
        cls,
        user: CustomUser,
        phone_number: str,
        submitted_otp: str,
    ) -> CustomUser:
        ensure_sms_available()
        phone_number = CustomUser.normalize_phone_number(phone_number)
        if user.phone_number:
            raise ValidationError(cls.generic_otp_error)

        def attach_verified_phone():
            try:
                with transaction.atomic():
                    locked_user = CustomUser.objects.select_for_update().get(pk=user.pk)
                    phone_is_owned = CustomUser.objects.filter(phone_number=phone_number).exclude(pk=user.pk).exists()
                    if not locked_user.is_active or locked_user.phone_number or phone_is_owned:
                        raise ValidationError(cls.generic_otp_error)
                    locked_user.phone_number = phone_number
                    locked_user.save(update_fields=["phone_number"])
                    return locked_user
            except (CustomUser.DoesNotExist, IntegrityError) as exc:
                raise ValidationError(cls.generic_otp_error) from exc

        locked_user = cls._guard(user, phone_number).verify(submitted_otp, on_success=attach_verified_phone)

        AppLogger.log_activity(
            msg="profile_phone_verification.completed",
            user=locked_user,
            status="INFO",
        )
        return locked_user
