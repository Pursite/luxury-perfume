import secrets

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.lib.security_cache import OTPVerificationGuard
from apps.lib.loggers import AppLogger
from apps.users.models import CustomUser
from apps.users.selectors import UserSelector
from apps.users.tasks import send_otp_sms_task


class SendOTPService:
    purpose = "signup"
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
    def send_signup_otp(cls, phone_number: str) -> dict:
        phone_number = CustomUser.normalize_phone_number(phone_number)

        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if user_exists:
            return cls._request_response()
        otp_code = cls._generate_otp_code()
        cls._guard(phone_number).store_code(otp_code)

        task = send_otp_sms_task.delay(phone_number, otp_code)

        AppLogger.log_activity(
            msg="OTP token generated and queued via Celery for signup",
            status="INFO",
            task_id=task.id,
        )

        return cls._request_response()

    @staticmethod
    def _request_response() -> dict:
        from django.conf import settings

        return {
            "message": "Verification code sent successfully.",
            "expires_in": settings.OTP_EXPIRY_SECONDS,
        }

    @classmethod
    def verify_signup_otp(cls, phone_number: str, submitted_otp: str) -> dict:
        phone_number = CustomUser.normalize_phone_number(phone_number)
        cls._guard(phone_number).verify(submitted_otp)

        try:
            with transaction.atomic():
                if UserSelector.check_user_exists_by_phone(phone_number):
                    raise ValidationError(cls.generic_otp_error)
                user = CustomUser.objects.create_user(phone_number=phone_number)
        except (DjangoValidationError, IntegrityError) as exc:
            raise ValidationError(cls.generic_otp_error) from exc

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg="User registered successfully via OTP", user=user, status="INFO")

        return {
            "message": "signup confirmed.",
            "tokens": tokens
        }
