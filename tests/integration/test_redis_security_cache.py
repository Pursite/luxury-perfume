import pytest
from django.core.cache import caches
from django.db import close_old_connections
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from apps.lib.security_cache import OTPVerificationGuard
from apps.lib.throttle import OTPIPRateThrottle, OTPPhoneNumberRateThrottle

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def make_request(factory, phone_number, ip):
    raw_request = factory.post(
        "/otp/",
        {"phone_number": phone_number},
        format="json",
        REMOTE_ADDR=ip,
    )
    return Request(raw_request, parsers=[JSONParser()])


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


def test_redis_otp_lockout_survives_a_new_code_request(settings):
    settings.OTP_VERIFICATION_MAX_ATTEMPTS = 2
    settings.OTP_VERIFICATION_LOCK_SECONDS = 60
    phone_number = "09123456789"
    guard = OTPVerificationGuard("login", phone_number)
    guard.store_code("123456")

    for _ in range(2):
        with pytest.raises(ValidationError):
            guard.verify("000000")

    guard.store_code("654321")

    with pytest.raises(Throttled, match="Too many verification attempts"):
        guard.verify("654321")


def test_redis_cache_aliases_keep_catalog_and_security_state_separate():
    caches["default"].set("same-key", "catalog")
    caches["security"].set("same-key", "security")

    assert caches["default"].get("same-key") == "catalog"
    assert caches["security"].get("same-key") == "security"


def test_redis_security_throttles_enforce_normalized_phone_and_ip_keys():
    factory = APIRequestFactory()
    first = make_request(factory, " 09123456789 ", "198.51.100.10")
    same_phone_other_ip = make_request(factory, "09123456789", "198.51.100.11")
    assert OTPPhoneNumberRateThrottle().allow_request(first, None) is True
    assert OTPPhoneNumberRateThrottle().allow_request(same_phone_other_ip, None) is False

    ip_requests = [
        make_request(factory, f"0912345678{index}", "198.51.100.10")
        for index in range(10)
    ]
    assert all(
        OTPIPRateThrottle().allow_request(request, None)
        for request in ip_requests
    )
    assert OTPIPRateThrottle().allow_request(
        make_request(factory, "09123456770", "198.51.100.10"),
        None,
    ) is False


def test_redis_otp_verification_allows_exactly_one_concurrent_consumer():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    phone_number = "09123456789"
    OTPVerificationGuard("login", phone_number).store_code("123456")
    ready = Barrier(2)

    def consume_code():
        close_old_connections()
        try:
            ready.wait(timeout=10)
            OTPVerificationGuard("login", phone_number).verify("123456")
            return "accepted"
        except (Throttled, ValidationError):
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume_code) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert sorted(results) == ["accepted", "rejected"]


def test_expired_lease_cannot_allow_two_successful_database_callbacks():
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from apps.users.tests.factories import UserFactory
    from apps.users.models import CustomUser

    user = UserFactory()
    guard = OTPVerificationGuard("login", user.phone_number)
    guard.store_code("123456")
    entered, finish = Event(), Event()

    def callback():
        entered.set()
        assert finish.wait(15)
        CustomUser.objects.filter(pk=user.pk).update(first_name="verified once")
        return "accepted"

    def verify(blocking=False):
        close_old_connections()
        try:
            return OTPVerificationGuard("login", user.phone_number).verify(
                "123456", on_success=callback if blocking else lambda: "accepted",
            )
        except (Throttled, ValidationError):
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(verify, True)
        try:
            assert entered.wait(5)
            old_owner = guard.cache.get(guard.lease_key)
            time.sleep(5.1)
            second = executor.submit(verify)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                new_owner = guard.cache.get(guard.lease_key)
                if new_owner and new_owner != old_owner:
                    break
                time.sleep(0.01)
            else:
                pytest.fail("second request did not acquire the expired lease")
            guard._release_lease(old_owner)
            assert guard.cache.get(guard.lease_key) == new_owner
        finally:
            finish.set()
        assert first.result(10) == "accepted"
        assert second.result(10) == "rejected"
    user.refresh_from_db()
    assert user.first_name == "verified once"


def test_resend_waits_for_redemption_and_old_cleanup_preserves_new_generation():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    guard = OTPVerificationGuard("login", "09123456789")
    guard.store_code("123456")
    entered, finish, resending = Event(), Event(), Event()

    def callback():
        entered.set()
        assert finish.wait(10)

    def verify():
        close_old_connections()
        try:
            guard.verify("123456", on_success=callback)
        finally:
            close_old_connections()

    def resend():
        close_old_connections()
        try:
            resending.set()
            return OTPVerificationGuard("login", "09123456789").store_code("654321")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(verify)
        try:
            assert entered.wait(5)
            second = executor.submit(resend)
            assert resending.wait(5)
        finally:
            finish.set()
        first.result(10)
        assert second.result(10) == "654321"
    with pytest.raises(ValidationError):
        guard.verify("123456")
    guard.verify("654321")


def test_postgres_rollback_keeps_redis_code_and_committed_cleanup_failure_cannot_replay(mocker):
    from django.db import DatabaseError
    from apps.users.models import CustomUser, OTPChallenge
    from apps.users.tests.factories import UserFactory

    user = UserFactory(first_name="original")
    guard = OTPVerificationGuard("login", user.phone_number)
    guard.store_code("123456")

    def fail_after_write():
        CustomUser.objects.filter(pk=user.pk).update(first_name="uncommitted")
        raise DatabaseError("simulated failure")

    with pytest.raises(DatabaseError):
        guard.verify("123456", on_success=fail_after_write)
    user.refresh_from_db()
    assert user.first_name == "original"
    assert OTPChallenge.objects.get(scope=guard.scope).redeemed_at is None
    mocker.patch.object(guard.cache, "delete_many", side_effect=OSError("cleanup unavailable"))
    guard.verify("123456", on_success=lambda: CustomUser.objects.filter(pk=user.pk).update(first_name="committed"))
    with pytest.raises(ValidationError):
        guard.verify("123456")
    user.refresh_from_db()
    assert user.first_name == "committed"


def test_failed_postgres_commit_preserves_code_and_rolls_back_redemption(mocker):
    from django.db import connection, DatabaseError
    from apps.users.models import CustomUser, OTPChallenge
    from apps.users.tests.factories import UserFactory

    user = UserFactory(first_name="original")
    guard = OTPVerificationGuard("login", user.phone_number)
    guard.store_code("123456")
    failed_commit = mocker.patch.object(connection, "commit", side_effect=DatabaseError("simulated commit failure"))
    with pytest.raises(DatabaseError):
        guard.verify("123456", on_success=lambda: CustomUser.objects.filter(pk=user.pk).update(first_name="uncommitted"))
    mocker.stop(failed_commit)
    user.refresh_from_db()
    assert user.first_name == "original"
    assert OTPChallenge.objects.get(scope=guard.scope).redeemed_at is None
    guard.verify("123456")
