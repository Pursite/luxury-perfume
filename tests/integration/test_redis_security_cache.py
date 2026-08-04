import pytest
from django.core.cache import caches
from rest_framework.exceptions import Throttled, ValidationError

from apps.lib.security_cache import OTPVerificationGuard


pytestmark = pytest.mark.integration


def test_redis_otp_consumption_is_visible_to_new_guard_instance():
    phone_number = "09123456789"
    OTPVerificationGuard("login", phone_number).store_code("123456")

    OTPVerificationGuard("login", phone_number).verify("123456")

    with pytest.raises(
        ValidationError,
        match="Invalid or expired verification code",
    ):
        OTPVerificationGuard("login", phone_number).verify("123456")


def test_redis_otp_lockout_survives_new_guard_instance(settings):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 2
    settings.OTP_VERIFICATION_LOCK_SECONDS = 60
    phone_number = "09123456789"
    OTPVerificationGuard("password-reset", phone_number).store_code("123456")

    for _ in range(2):
        with pytest.raises(ValidationError):
            OTPVerificationGuard("password-reset", phone_number).verify("000000")

    with pytest.raises(Throttled, match="Too many verification attempts"):
        OTPVerificationGuard("password-reset", phone_number).verify("123456")


def test_redis_cache_aliases_keep_catalog_and_security_state_separate():
    caches["default"].set("same-key", "catalog")
    caches["security"].set("same-key", "security")

    assert caches["default"].get("same-key") == "catalog"
    assert caches["security"].get("same-key") == "security"

