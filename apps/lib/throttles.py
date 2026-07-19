from rest_framework.throttling import SimpleRateThrottle


class OTPPhoneRateThrottle(SimpleRateThrottle):
    scope = 'otp_phone'

    def get_rate(self):
        return "1/2min"

    def parse_rate(self, rate):
        return (1, 120)

    def get_cache_key(self, request, view):
        if request.method != 'POST':
            return None

        phone_number = request.data.get('phone_number')

        if not phone_number:
            return None

        return self.cache_format % {
            'scope': self.scope,
            'ident': phone_number
        }


