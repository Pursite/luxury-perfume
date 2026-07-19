import random

from rest_framework.exceptions import ValidationError, AuthenticationFailed
from apps.lib.loggers import AppLogger
from ..selectors import UserSelector
from ..tasks import send_otp_sms_task
from ...lib.cache import RedisCacheService


class LoginOtpService:
    @staticmethod
    def _generate_otp_code() -> str:
        return str(random.randint(100000, 999999))

    @classmethod
    def login_with_username_password(cls, username: str, password: str) -> dict:
        user = UserSelector.authenticate_by_username_password(username=username, password=password)

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg="User logged in successfully via username/password", user=user, status="INFO")

        return {
            "message": "successfully logged in.",
            "tokens": tokens
        }

    @classmethod
    def send_login_otp(cls, phone_number: str) -> dict:
        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if not user_exists:
            AppLogger.log_security(msg=f"Login OTP requested for non-existent phone: {phone_number}")
            raise ValidationError({
                "phone_number": "no user found with this phone number."
            })

        otp_code = cls._generate_otp_code()

        cache_key = f"otp_login_{phone_number}"
        cache_success = RedisCacheService.set(cache_key, otp_code, timeout=120)

        if not cache_success:
            AppLogger.log_system_error(f"Redis operation failed during login OTP generation for: {phone_number}")
            raise ValidationError({
                "system": "please try again later."
            })

        send_otp_sms_task.delay(phone_number, otp_code)

        AppLogger.log_activity(msg=f"Login OTP token generated and queued via Celery", status="INFO")

        return {
            "message": "otp code successfully sent.",
            "expires_in": 120
        }

    @classmethod
    def verify_login_otp(cls, phone_number: str, submitted_otp: str) -> dict:
        cache_key = f"otp_login_{phone_number}"

        saved_otp = RedisCacheService.get(cache_key)

        if not saved_otp:
            AppLogger.log_security(
                msg=f"Login OTP verification failed: Code expired or never requested for {phone_number}")
            raise ValidationError({"otp": "otp code expired or there is no request."})

        if saved_otp != submitted_otp:
            AppLogger.log_security(msg=f"Login OTP verification failed: Wrong code submitted for {phone_number}")
            raise ValidationError({"otp": "invalid otp."})

        user = UserSelector.get_user_by_phone(phone_number)
        if not user:
            raise ValidationError({"phone_number": "no user found."})

        if not user.is_active:
            raise AuthenticationFailed("your account is deactivated.")

        RedisCacheService.delete(cache_key)

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg="User logged in successfully via OTP", user=user, status="INFO")

        return {
            "message": "successfully logged in.",
            "tokens": tokens
        }