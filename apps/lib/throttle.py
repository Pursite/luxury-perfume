from rest_framework.throttling import SimpleRateThrottle

class OTPPhoneNumberRateThrottle(SimpleRateThrottle):
    scope = "otp"

    def get_cache_key(self, request, view):
        phone_number = request.data.get("phone_number")

        if phone_number:
            ident = phone_number
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident
        }