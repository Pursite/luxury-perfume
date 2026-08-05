import secrets

from django.db import transaction
from rest_framework.exceptions import ValidationError
from apps.lib.loggers import AppLogger
from apps.lib.security_cache import OTPVerificationGuard
from apps.users.models import CustomUser
from apps.users.selectors import UserSelector
from apps.users.tasks import send_otp_sms_task
from apps.users.jwt import revoke_user_refresh_tokens


class PasswordResetService:
    purpose = "password-reset"
    generic_otp_error = {"otp": "Invalid or expired verification code."}

    @staticmethod
    def _generate_otp_code() -> str:
        return f"{secrets.randbelow(900000) + 100000:06d}"

    @classmethod
    def _guard(cls, phone_number: str) -> OTPVerificationGuard:
        return OTPVerificationGuard(cls.purpose, CustomUser.normalize_phone_number(phone_number))

    @classmethod
    def _attempt_key(cls, phone_number: str) -> str:
        return cls._guard(phone_number).attempts_key

    @classmethod
    def send_reset_otp(cls, phone_number: str) -> dict:
        phone_number = CustomUser.normalize_phone_number(phone_number)
        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if not user_exists:
            AppLogger.log_security(msg="Password reset requested for an unknown phone.")
            return cls._request_response()

        otp_code = cls._generate_otp_code()
        cls._guard(phone_number).store_code(otp_code)

        send_otp_sms_task.delay(phone_number, otp_code)

        AppLogger.log_activity(msg="Password reset OTP generated and queued via Celery", status="INFO")

        return cls._request_response()

    @staticmethod
    def _request_response() -> dict:
        from django.conf import settings

        return {
            "message": "password reset otp code successfully sent.",
            "expires_in": settings.OTP_EXPIRY_SECONDS,
        }


    @classmethod
    def verify_and_reset_password(cls, phone_number: str, submitted_otp: str, new_password: str) -> dict:
        phone_number = CustomUser.normalize_phone_number(phone_number)
        cls._guard(phone_number).verify(submitted_otp)

        with transaction.atomic():
            user = CustomUser.objects.select_for_update().filter(
                phone_number=phone_number,
                is_active=True,
            ).first()
            if not user:
                raise ValidationError(cls.generic_otp_error)
            user.set_password(new_password)
            revoke_user_refresh_tokens(user)
            user.save()

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg="User password reset successfully via OTP", user=user, status="INFO")

        return {
            "message": "password changed successfully.",
            "tokens": tokens
        }
