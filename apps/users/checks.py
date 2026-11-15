from ipaddress import ip_network

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_auth_proxy_settings(app_configs, **kwargs):
    if not settings.AUTH_TRUST_PROXY_HEADERS:
        return []
    try:
        networks = [
            ip_network(value, strict=False)
            for value in settings.AUTH_TRUSTED_PROXY_CIDRS
        ]
    except ValueError:
        networks = []
    if not networks:
        return [
            Error(
                "Authentication proxy trust requires valid, explicit proxy CIDRs.",
                id="users.E001",
            )
        ]
    return []
