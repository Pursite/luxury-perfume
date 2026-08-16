import pytest
from django.core.cache import caches
from django.db import close_old_connections
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from apps.lib.security_cache import OTPVerificationGuard
from apps.lib.throttle import OTPIPRateThrottle, OTPPhoneNumberRateThrottle

pytestmark = pytest.mark.integration


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
