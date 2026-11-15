import pytest
from django.core.cache import caches
from rest_framework.exceptions import Throttled, ValidationError

from apps.lib.security_cache import OTPVerificationGuard, SecurityCacheUnavailable


pytestmark = pytest.mark.django_db(transaction=True)

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


def test_otp_lockout_survives_a_new_code_request(settings):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 5
    settings.OTP_VERIFICATION_LOCK_SECONDS = 300
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")

    for _ in range(5):
        with pytest.raises(
            ValidationError,
            match="Invalid or expired verification code",
        ):
            guard.verify("000000")

    guard.store_code("654321")

    assert caches["security"].get(guard.lock_key) == 1
    with pytest.raises(Throttled, match="Too many verification attempts"):
        guard.verify("654321")


def test_otp_verification_rechecks_a_lock_acquired_before_lease(mocker):
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    original_add = guard.cache.add

    def acquire_lease_after_lock(key, value, timeout=None, version=None):
        if key == guard.lease_key:
            guard.cache.set(guard.lock_key, 1, timeout=60)
        return original_add(key, value, timeout=timeout, version=version)

    mocker.patch.object(guard.cache, "add", side_effect=acquire_lease_after_lock)

    with pytest.raises(Throttled, match="Too many verification attempts"):
        guard.verify("123456")

    assert caches["security"].get(guard.code_key)["code"] == "123456"


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

    assert caches["security"].get(guard.code_key)["code"] == "123456"


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


@pytest.mark.django_db(transaction=True)
def test_committed_redemption_survives_cache_cleanup_failure(mocker):
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    callback = mocker.Mock(return_value="accepted")
    mocker.patch.object(guard.cache, "delete_many", side_effect=OSError("unavailable"))
    assert guard.verify("123456", on_success=callback) == "accepted"
    with pytest.raises(ValidationError):
        guard.verify("123456", on_success=callback)
    callback.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_database_failure_rolls_back_account_change_and_preserves_otp():
    from django.db import DatabaseError, transaction
    from apps.users.tests.factories import UserFactory

    user = UserFactory()
    guard = OTPVerificationGuard("login", user.phone_number)
    guard.store_code("123456")

    def failing_callback():
        with transaction.atomic():
            type(user).objects.filter(pk=user.pk).update(first_name="should rollback")
            raise DatabaseError("simulated database failure")

    with pytest.raises(DatabaseError):
        guard.verify("123456", on_success=failing_callback)
    user.refresh_from_db()
    assert user.first_name != "should rollback"
    guard.verify("123456")


def test_resend_replaces_generation_and_never_repeats_active_code():
    from apps.users.models import OTPChallenge
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    first = OTPChallenge.objects.get(scope=guard.scope).generation
    new_code = guard.store_code("123456")
    assert new_code != "123456"
    assert OTPChallenge.objects.get(scope=guard.scope).generation != first
    with pytest.raises(ValidationError):
        guard.verify("123456")
    guard.verify(new_code)


@pytest.mark.parametrize("invalid_state", ["expired", "generation-mismatch", "legacy-code"])
def test_otp_rejects_invalid_durable_or_cached_state(invalid_state):
    from django.utils import timezone
    from datetime import timedelta
    from apps.users.models import OTPChallenge
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    if invalid_state == "expired":
        OTPChallenge.objects.filter(scope=guard.scope).update(expires_at=timezone.now() - timedelta(seconds=1))
    elif invalid_state == "generation-mismatch":
        guard.cache.set(guard.code_key, {"generation": "wrong", "code": "123456"})
    else:
        guard.cache.set(guard.code_key, "123456")
    with pytest.raises(ValidationError):
        guard.verify("123456")


def test_old_request_cannot_release_new_lease():
    guard = OTPVerificationGuard("login", "09123456789")
    guard.cache.set(guard.lease_key, "new-owner")
    guard._release_lease("old-owner")
    assert guard.cache.get(guard.lease_key) == "new-owner"


def test_issuance_rollback_never_accepts_uncommitted_cache_generation():
    from django.db import transaction
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            guard.store_code("654321")
            raise RuntimeError("rollback issuance")
    with pytest.raises(ValidationError):
        guard.verify("654321")
    replacement = guard.store_code("987654")
    guard.verify(replacement)


def test_expired_challenge_cleanup_preserves_active_challenges():
    from django.core.management import call_command
    from django.utils import timezone
    from datetime import timedelta
    from apps.users.models import OTPChallenge
    expired = OTPVerificationGuard("login", "09123456789")
    active = OTPVerificationGuard("login", "09123456788")
    expired.store_code("123456")
    active.store_code("654321")
    OTPChallenge.objects.filter(scope=expired.scope).update(expires_at=timezone.now() - timedelta(seconds=1))
    call_command("cleanup_otp_challenges")
    assert not OTPChallenge.objects.filter(scope=expired.scope).exists()
    active.verify("654321")


@pytest.mark.parametrize("operation", ["add", "incr", "set"])
def test_verification_cache_mutation_failures_do_not_authorize_callback(mocker, settings, operation):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 1
    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    callback = mocker.Mock()
    mocker.patch.object(guard.cache, operation, side_effect=OSError("unavailable"))
    with pytest.raises(SecurityCacheUnavailable):
        guard.verify("000000", on_success=callback)
    callback.assert_not_called()
