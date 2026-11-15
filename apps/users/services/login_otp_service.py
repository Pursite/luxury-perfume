import secrets

from django.db import transaction

from rest_framework.exceptions import ValidationError, AuthenticationFailed
from apps.lib.security_cache import OTPVerificationGuard, PasswordLoginGuard
from apps.lib.loggers import AppLogger
from ..selectors import UserSelector
from ..tasks import send_otp_sms_task
from ..models import CustomUser
from ..jwt import issue_tokens_for_user

from .sms_availability import ensure_sms_available


class LoginOtpService:
    purpose = "login"
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
    def login_with_username_password(
        cls,
        username: str,
        password: str,
        client_ip: str = "unknown",
    ) -> dict:
        username = CustomUser.normalize_username(username)
        guard = PasswordLoginGuard(username, client_ip)
        guard.ensure_unlocked()
        try:
            user = UserSelector.authenticate_by_username_password(
                username=username,
                password=password,
            )
        except AuthenticationFailed:
            guard.record_failure()
            raise
        guard.clear()

        tokens = issue_tokens_for_user(user)

        AppLogger.log_activity(msg="User logged in successfully via username/password", user=user, status="INFO")

        return {
            "message": "successfully logged in.",
            "tokens": tokens
        }

    @classmethod
    def send_login_otp(cls, phone_number: str) -> dict:
        ensure_sms_available()
        phone_number = CustomUser.normalize_phone_number(phone_number)
        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if not user_exists:
            AppLogger.log_security(msg="Login OTP requested for an unknown phone.")
            return cls._request_response()

        otp_code = cls._generate_otp_code()
        otp_code = cls._guard(phone_number).store_code(otp_code)

        transaction.on_commit(lambda: send_otp_sms_task.delay(phone_number, otp_code))

        AppLogger.log_activity(
            msg="Login OTP token generated and queued via Celery",
            status="INFO",
        )

        return cls._request_response()

    @staticmethod
    def _request_response() -> dict:
        from django.conf import settings

        return {
            "message": "otp code successfully sent.",
            "expires_in": settings.OTP_EXPIRY_SECONDS,
        }

    @classmethod
    def verify_login_otp(cls, phone_number: str, submitted_otp: str) -> dict:
        ensure_sms_available()
        phone_number = CustomUser.normalize_phone_number(phone_number)

        def authenticate_verified_user():
            user = CustomUser.objects.select_for_update().filter(phone_number=phone_number, is_active=True).first()
            if not user:
                raise ValidationError(cls.generic_otp_error)
            return user, issue_tokens_for_user(user)

        user, tokens = cls._guard(phone_number).verify(submitted_otp, on_success=authenticate_verified_user)

        AppLogger.log_activity(msg="User logged in successfully via OTP", user=user, status="INFO")

        return {
            "message": "successfully logged in.",
            "tokens": tokens
        }
