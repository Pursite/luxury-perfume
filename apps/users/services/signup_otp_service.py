import random

from rest_framework.exceptions import ValidationError

from apps.lib.cache import RedisCacheService
from apps.lib.loggers import AppLogger
from apps.users.models import CustomUser
from apps.users.selectors import UserSelector
from apps.users.tasks import send_otp_sms_task


class SendOTPService:

    @staticmethod
    def _generate_otp_code() -> str:
        return str(random.randint(100000, 999999))

    @classmethod
    def send_signup_otp(cls, phone_number: str) -> dict:

        user_exists = UserSelector.check_user_exists_by_phone(phone_number)
        if user_exists:
            raise ValidationError({
                "phone_number": "some one signed up with this phone number."
            })
        otp_code = cls._generate_otp_code()

        cache_key = f"otp_signup_{phone_number}"
        cache_success = RedisCacheService.set(cache_key, otp_code, timeout=120)

        if not cache_success:
            AppLogger.log_system_error(f"Redis operation failed during signup OTP generation for: {phone_number}")
            raise ValidationError({
                "system": "please try again later."
            })

        send_otp_sms_task.delay(phone_number, otp_code)

        AppLogger.log_activity(msg=f"OTP token generated and queued via Celery for signup", status="INFO")

        return {
            "message": "otp code has been sent.",
            "expires_in": 120
        }


    @classmethod
    def verify_signup_otp(cls, phone_number: str, submitted_otp: str) -> dict:
        cache_key = f"otp_signup_{phone_number}"

        saved_otp = RedisCacheService.get(cache_key)

        if not saved_otp:
            AppLogger.log_security(msg=f"OTP verification failed: Code expired or never requested for {phone_number}")
            raise ValidationError({"otp": "otp code expired or never requested for {phone_number}."})

        if saved_otp != submitted_otp:
            raise ValidationError({"otp": "otp code is wrong."})

        if UserSelector.check_user_exists_by_phone(phone_number):
            raise ValidationError({"phone_number": "user already exists."})

        user = CustomUser.objects.create_user(phone_number=phone_number)

        RedisCacheService.delete(cache_key)

        tokens = UserSelector.generate_tokens_for_user(user)

        AppLogger.log_activity(msg=f"User registered successfully via OTP", user=user, status="INFO")

        return {
            "message": "signup confirmed.",
            "tokens": tokens
        }