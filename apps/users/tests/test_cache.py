import pytest
from django.core.cache import caches
from rest_framework.exceptions import Throttled, ValidationError

from apps.lib.security_cache import OTPVerificationGuard, SecurityCacheUnavailable


def test_otp_verification_consumes_code_and_clears_security_state():
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    caches["security"].set(guard.attempts_key, 1)
    caches["security"].set(guard.lock_key, 0)

    guard.verify("123456")

    assert caches["security"].get(guard.code_key) is None
    assert caches["security"].get(guard.attempts_key) is None
    assert caches["security"].get(guard.lock_key) is None
    assert caches["security"].get(guard.lease_key) is None
    with pytest.raises(
        ValidationError,
        match="Invalid or expired verification code",
    ):
        guard.verify("123456")


def test_otp_verification_locks_after_exact_failure_threshold(settings):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 2
    settings.OTP_VERIFICATION_LOCK_SECONDS = 60
    guard = OTPVerificationGuard("password-reset", "09123456789")
    guard.store_code("123456")

    for expected_attempts in (1, 2):
        with pytest.raises(
            ValidationError,
            match="Invalid or expired verification code",
        ):
            guard.verify("000000")
        assert caches["security"].get(guard.attempts_key) == expected_attempts

    assert caches["security"].get(guard.lock_key) == 1
    with pytest.raises(Throttled, match="Too many verification attempts"):
        guard.verify("123456")


def test_otp_purpose_namespaces_are_isolated():
    signup = OTPVerificationGuard("signup", "09123456789")
    login = OTPVerificationGuard("login", "09123456789")
    password_reset = OTPVerificationGuard("password-reset", "09123456789")

    assert len(
        {signup.code_key, login.code_key, password_reset.code_key}
    ) == 3
    assert len(
        {signup.attempts_key, login.attempts_key, password_reset.attempts_key}
    ) == 3


def test_existing_verification_lease_rejects_concurrent_attempt():
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    caches["security"].set(guard.lease_key, 1, timeout=5)

    with pytest.raises(Throttled, match="already in progress"):
        guard.verify("123456")

    assert caches["security"].get(guard.code_key) == "123456"


@pytest.mark.parametrize("operation", ["store", "verify"])
def test_security_cache_failures_fail_closed(mocker, operation):
    guard = OTPVerificationGuard("signup", "09123456789")
    if operation == "store":
        mocker.patch.object(
            guard.cache,
            "set",
            side_effect=OSError("cache unavailable"),
        )
        def action():
            guard.store_code("123456")
    else:
        mocker.patch.object(
            guard.cache,
            "get",
            side_effect=OSError("cache unavailable"),
        )
        def action():
            guard.verify("123456")

    with pytest.raises(SecurityCacheUnavailable) as exc_info:
        action()

    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in str(exc_info.value.detail)
