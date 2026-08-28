from apps.lib.client_ip import get_trusted_client_ip
from apps.lib.throttle import SecurityCacheRateThrottle


class PaymentInitializeRateThrottle(SecurityCacheRateThrottle):
    scope = "payment_initialize"

    def get_cache_key(self, request, view):
        user = request.user
        ident = f"user:{user.pk}" if user and user.is_authenticated else "anonymous"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PaymentCallbackRateThrottle(SecurityCacheRateThrottle):
    scope = "payment_callback"

    def get_cache_key(self, request, view):
        ident = get_trusted_client_ip(request) or "invalid"
        return self.cache_format % {"scope": self.scope, "ident": ident}
