from django.core.cache import caches
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

from apps.lib.security_cache import SecurityCacheUnavailable
from apps.users.models import CustomUser


class SecurityCacheRateThrottle(SimpleRateThrottle):
    """DRF rate throttle backed by fail-closed authentication security state."""

    def __init__(self):
        super().__init__()
        self.cache = caches["security"]

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            raise SecurityCacheUnavailable from exc

class OTPPhoneNumberRateThrottle(SecurityCacheRateThrottle):
    scope = "otp"

    def get_cache_key(self, request, view):
        phone_number = CustomUser.normalize_phone_number(
            request.data.get("phone_number")
        )
        if CustomUser.is_valid_phone_number(phone_number):
            ident = phone_number
        else:
            ident = f"invalid:{self.get_ident(request)}"

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident
        }


class OTPVerificationRateThrottle(OTPPhoneNumberRateThrottle):
    scope = "otp_verify"


class OTPIPRateThrottle(SecurityCacheRateThrottle):
    scope = "otp_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class OTPVerificationIPRateThrottle(OTPIPRateThrottle):
    scope = "otp_verify_ip"


class PasswordLoginRateThrottle(AnonRateThrottle):
    scope = "login"

class SignupRateThrottle(AnonRateThrottle):
    """A dedicated anonymous registration limit, keyed by client IP."""

    scope = "signup"
