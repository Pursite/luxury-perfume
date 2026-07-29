import secrets
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from apps.lib.loggers import AppLogger
from apps.lib.cache import RedisCacheService
from apps.users.selectors import UserSelector
from apps.users.tasks import send_otp_sms_task


class PasswordResetService:

    @staticmethod
    def _generate_otp_code() -> str:
        return f"{secrets.randbelow(900000) + 100000:06d}"

    @classmethod
    def send_reset_otp(cls, phone_number: str) -> dict:
        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if not user_exists:
            AppLogger.log_security(msg=f"Password reset requested for non-existent phone: {phone_number}")
            raise ValidationError({
                "phone_number": "no user found with this phone number."
            })

        otp_code = cls._generate_otp_code()
        cache_key = f"otp_reset_{phone_number}"

        cache_success = RedisCacheService.set(cache_key, otp_code, timeout=120)

        if not cache_success:
            AppLogger.log_system_error(
                f"Redis operation failed during password reset OTP generation for: {phone_number}")
            raise ValidationError({
                "system": "please try again later."
            })

        send_otp_sms_task.delay(phone_number, otp_code)

        AppLogger.log_activity(msg="Password reset OTP generated and queued via Celery", status="INFO")

        return {
            "message": "password reset otp code successfully sent.",
            "expires_in": 120
        }


    @classmethod
    def verify_and_reset_password(cls, phone_number: str, submitted_otp: str, new_password: str) -> dict:
        cache_key = f"otp_reset_{phone_number}"

        saved_otp = RedisCacheService.get(cache_key)

        if not saved_otp:
            AppLogger.log_security(
                msg=f"Password reset verification failed: Code expired or never requested for {phone_number}"
            )
            raise ValidationError({"otp": "otp code expired or there is no request."})

        if saved_otp != submitted_otp:
            AppLogger.log_security(msg=f"Password reset verification failed: Wrong code submitted for {phone_number}")
            raise ValidationError({"otp": "invalid otp."})

        user = UserSelector.get_user_by_phone(phone_number)
        if not user:
            raise ValidationError({"phone_number": "no user found."})

        if not user.is_active:
            raise AuthenticationFailed("your account is deactivated.")

        user.set_password(new_password)
        user.save()

        RedisCacheService.delete(cache_key)

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg="User password reset successfully via OTP", user=user, status="INFO")

        return {
            "message": "password changed successfully.",
            "tokens": tokens
        }
