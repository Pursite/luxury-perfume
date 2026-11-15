"""Authenticated password operations, separate from account recovery."""

from secrets import randbelow

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from apps.lib.security_cache import OTPVerificationGuard
from apps.users.jwt import revoke_user_refresh_tokens
from apps.users.models import CustomUser
from apps.users.password_policy import validate_password_policy
from apps.users.tasks import send_otp_sms_task
from .sms_availability import ensure_sms_available


@transaction.atomic
def change_password(*, user, current_password, password):
    user = CustomUser.objects.select_for_update().get(pk=user.pk)
    if not user.is_active or not user.has_usable_password():
        raise ValidationError(
            {"current_password": _("Use verified initial password setup.")}
        )
    if not user.check_password(current_password):
        raise ValidationError({"current_password": _("Current password is incorrect.")})
    validate_password_policy(password, user)
    user.set_password(password)
    user.save(update_fields=["password", "updated_at"])
    revoke_user_refresh_tokens(user)
    return user


def setup_guard(user):
    return OTPVerificationGuard(f"password-set:{user.pk}", user.phone_number)


def _ensure_setup_eligible(user):
    if not user.is_active or user.has_usable_password() or not user.phone_number:
        raise ValidationError(
            {
                "detail": _(
                    "Verified initial password setup is unavailable for this account."
                )
            }
        )


def send_setup_otp(*, user):
    ensure_sms_available()
    _ensure_setup_eligible(user)
    code = setup_guard(user).store_code(f"{randbelow(900000) + 100000:06d}")
    transaction.on_commit(lambda: send_otp_sms_task.delay(user.phone_number, code))
    return {
        "message": "Verification code sent successfully.",
        "expires_in": settings.OTP_EXPIRY_SECONDS,
    }


def set_initial_password(*, user, otp, password):
    ensure_sms_available()
    _ensure_setup_eligible(user)

    def verified_setup():
        locked_user = CustomUser.objects.select_for_update().get(pk=user.pk)
        _ensure_setup_eligible(locked_user)
        if locked_user.phone_number != user.phone_number:
            raise ValidationError({"otp": _("Invalid or expired verification code.")})
        validate_password_policy(password, locked_user)
        locked_user.set_password(password)
        locked_user.save(update_fields=["password", "updated_at"])
        revoke_user_refresh_tokens(locked_user)
        return locked_user

    return setup_guard(user).verify(otp, on_success=verified_setup)
