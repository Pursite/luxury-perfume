"""Fail-closed cache helpers for authentication security controls."""

import logging
from contextlib import nullcontext
from datetime import timedelta
from secrets import compare_digest, randbelow
from threading import RLock
from uuid import uuid4

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django_redis.cache import RedisCache
from django.utils.translation import gettext, gettext_lazy
from rest_framework.exceptions import APIException, Throttled, ValidationError

from apps.users.models import OTPChallenge


logger = logging.getLogger("security")
_local_lease_mutex = RLock()


class SecurityCacheUnavailable(APIException):
    status_code = 503
    default_detail = gettext_lazy(
        "Authentication protection is temporarily unavailable. Please try again later."
    )


class OTPVerificationGuard:
    def __init__(self, purpose: str, phone_number: str):
        self.cache = caches["security"]
        self.prefix = f"security:otp:{purpose}:{phone_number}"

    @property
    def code_key(self):
        return f"{self.prefix}:code"

    @property
    def attempts_key(self):
        return f"{self.prefix}:attempts"

    @property
    def lock_key(self):
        return f"{self.prefix}:locked"

    @property
    def lease_key(self):
        return f"{self.prefix}:lease"

    @property
    def scope(self):
        return salted_hmac("otp-scope", self.prefix, algorithm="sha256").hexdigest()

    def _cache(self, operation, *args, **kwargs):
        try:
            return getattr(self.cache, operation)(*args, **kwargs)
        except Exception as exc:
            raise SecurityCacheUnavailable from exc

    def _compare_delete(self, key, expected):
        # Redis performs ownership comparison and deletion in one operation.
        if isinstance(self.cache, RedisCache):
            client = self.cache.client
            return client.get_client(write=True).eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                client.make_key(key),
                client.encode(expected),
            )
        if isinstance(self.cache, LocMemCache):
            # Only the self-contained test backend uses this process-local path.
            with _local_lease_mutex:
                if self.cache.get(key) == expected:
                    return self.cache.delete(key)
            return False
        raise SecurityCacheUnavailable

    def _release_lease(self, token):
        try:
            self._compare_delete(self.lease_key, token)
        except Exception:
            logger.warning("otp.lease_cleanup_failed")

    def _cleanup(self, generation):
        try:
            with transaction.atomic():
                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(scope=self.scope)
                    .first()
                )
                if (
                    challenge
                    and challenge.generation == generation
                    and challenge.redeemed_at
                ):
                    self.cache.delete_many(
                        [self.code_key, self.attempts_key, self.lock_key]
                    )
        except Exception:
            # A committed redemption is authoritative even if cache cleanup fails.
            logger.warning("otp.redemption_cleanup_failed")

    def store_code(self, code: str) -> str:
        with transaction.atomic():
            OTPChallenge.objects.get_or_create(
                scope=self.scope,
                defaults={"generation": uuid4(), "expires_at": timezone.now()},
            )
            challenge = OTPChallenge.objects.select_for_update().get(scope=self.scope)
            previous = self._cache("get", self.code_key)
            if isinstance(previous, dict) and previous.get("code") == code:
                # Do not let an immediate resend accidentally repeat the active code.
                while previous["code"] == code:
                    code = f"{randbelow(900000) + 100000:06d}"
            challenge.generation = uuid4()
            challenge.expires_at = timezone.now() + timedelta(
                seconds=settings.OTP_EXPIRY_SECONDS
            )
            challenge.redeemed_at = None
            challenge.save()
            self._cache(
                "set",
                self.code_key,
                {"generation": str(challenge.generation), "code": code},
                settings.OTP_EXPIRY_SECONDS,
            )
            return code

    def _ensure_unlocked(self):
        if self._cache("get", self.lock_key):
            raise Throttled(
                detail=gettext(
                    "Too many verification attempts. Please try again later."
                )
            )

    def _invalid(self):
        self._cache("add", self.attempts_key, 0, timeout=settings.OTP_EXPIRY_SECONDS)
        if (
            self._cache("incr", self.attempts_key)
            >= settings.OTP_VERIFICATION_MAX_ATTEMPTS
        ):
            self._cache("set", self.lock_key, 1, settings.OTP_VERIFICATION_LOCK_SECONDS)
        raise ValidationError({"otp": gettext("Invalid or expired verification code.")})

    def verify(self, submitted: str, on_success=None):
        self._ensure_unlocked()
        token = str(uuid4())
        with (
            _local_lease_mutex if isinstance(self.cache, LocMemCache) else nullcontext()
        ):
            acquired = self._cache("add", self.lease_key, token, timeout=5)
        if not acquired:
            raise Throttled(
                detail=gettext("Verification is already in progress. Please try again.")
            )
        try:
            with transaction.atomic():
                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(scope=self.scope)
                    .first()
                )
                self._ensure_unlocked()
                saved = self._cache("get", self.code_key)
                if (
                    not challenge
                    or challenge.redeemed_at
                    or challenge.expires_at <= timezone.now()
                    or not isinstance(saved, dict)
                    or saved.get("generation") != str(challenge.generation)
                    or not compare_digest(str(saved.get("code", "")), str(submitted))
                ):
                    self._invalid()
                result = on_success() if on_success is not None else None
                challenge.redeemed_at = timezone.now()
                challenge.save(update_fields=["redeemed_at"])
                transaction.on_commit(lambda: self._cleanup(challenge.generation))
                return result
        finally:
            self._release_lease(token)


class PasswordLoginGuard:
    """Temporarily slow repeated credential guesses without leaking account state."""

    def __init__(self, username: str, client_ip: str):
        self.cache = caches["security"]
        self.prefix = f"security:password-login:{username.casefold()}:ip:{client_ip}"

    @property
    def attempts_key(self):
        return f"{self.prefix}:attempts"

    @property
    def lock_key(self):
        return f"{self.prefix}:locked"

    def ensure_unlocked(self) -> None:
        try:
            if self.cache.get(self.lock_key):
                raise Throttled(
                    detail=gettext("Too many login attempts. Please try again later.")
                )
        except Throttled:
            raise
        except Exception as exc:
            raise SecurityCacheUnavailable from exc

    def record_failure(self) -> None:
        try:
            self.cache.add(
                self.attempts_key,
                0,
                timeout=settings.PASSWORD_LOGIN_LOCK_SECONDS,
            )
            attempts = self.cache.incr(self.attempts_key)
            if attempts >= settings.PASSWORD_LOGIN_MAX_ATTEMPTS:
                self.cache.set(self.lock_key, 1, settings.PASSWORD_LOGIN_LOCK_SECONDS)
        except Exception as exc:
            raise SecurityCacheUnavailable from exc

    def clear(self) -> None:
        try:
            self.cache.delete_many([self.attempts_key, self.lock_key])
        except Exception as exc:
            raise SecurityCacheUnavailable from exc
