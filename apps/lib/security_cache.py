"""Fail-closed cache helpers for authentication security controls."""

from django.conf import settings
from django.core.cache import caches
from django.utils.translation import gettext, gettext_lazy
from rest_framework.exceptions import APIException, Throttled, ValidationError


class SecurityCacheUnavailable(APIException):
    status_code = 503
    default_detail = gettext_lazy("Authentication protection is temporarily unavailable. Please try again later.")


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

    def store_code(self, code: str) -> None:
        try:
            self.cache.set(self.code_key, code, settings.OTP_EXPIRY_SECONDS)
        except Exception as exc:
            raise SecurityCacheUnavailable from exc

    def verify(self, submitted: str, on_success=None):
        lease = self.lease_key
        try:
            if self.cache.get(self.lock_key):
                raise Throttled(
                    detail=gettext("Too many verification attempts. Please try again later.")
                )
            if not self.cache.add(lease, 1, timeout=5):
                raise Throttled(
                    detail=gettext("Verification is already in progress. Please try again.")
                )
            try:
                if self.cache.get(self.lock_key):
                    raise Throttled(
                        detail=gettext("Too many verification attempts. Please try again later.")
                    )
                saved = self.cache.get(self.code_key)
                from secrets import compare_digest

                if not saved or not compare_digest(str(saved), str(submitted)):
                    self.cache.add(self.attempts_key, 0, timeout=settings.OTP_EXPIRY_SECONDS)
                    if self.cache.incr(self.attempts_key) >= settings.OTP_VERIFICATION_MAX_ATTEMPTS:
                        self.cache.set(self.lock_key, 1, settings.OTP_VERIFICATION_LOCK_SECONDS)
                    raise ValidationError({"otp": gettext("Invalid or expired verification code.")})
                result = on_success() if on_success is not None else None
                self.cache.delete_many([self.code_key, self.attempts_key, self.lock_key])
                return result
            finally:
                self.cache.delete(lease)
        except (Throttled, ValidationError):
            raise
        except Exception as exc:
            raise SecurityCacheUnavailable from exc


class PasswordLoginGuard:
    """Temporarily slow repeated credential guesses without leaking account state."""

    def __init__(self, username: str, client_ip: str):
        self.cache = caches["security"]
        self.prefix = (
            f"security:password-login:{username.casefold()}:ip:{client_ip}"
        )

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
