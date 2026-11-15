from django.test import RequestFactory, override_settings

from apps.lib.client_ip import get_trusted_client_ip


def _request(*, remote_addr, forwarded_for=None):
    headers = {"REMOTE_ADDR": remote_addr}
    if forwarded_for is not None:
        headers["HTTP_X_FORWARDED_FOR"] = forwarded_for
    return RequestFactory().get("/", **headers)


@override_settings(PAYMENT_TRUST_PROXY_HEADERS=False, PAYMENT_TRUSTED_PROXY_CIDRS=())
def test_client_ip_ignores_forwarding_header_when_trust_is_disabled():
    request = _request(remote_addr="203.0.113.8", forwarded_for="198.51.100.4")

    assert get_trusted_client_ip(request) == "203.0.113.8"


@override_settings(
    PAYMENT_TRUST_PROXY_HEADERS=True,
    PAYMENT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
)
def test_client_ip_walks_trusted_proxy_chain_from_right_to_left():
    request = _request(
        remote_addr="10.0.0.2",
        forwarded_for="198.51.100.4, 10.0.0.3",
    )

    assert get_trusted_client_ip(request) == "198.51.100.4"


@override_settings(
    PAYMENT_TRUST_PROXY_HEADERS=True,
    PAYMENT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
)
def test_client_ip_rejects_spoofed_or_malformed_forwarding_chains():
    untrusted_peer = _request(
        remote_addr="203.0.113.8",
        forwarded_for="198.51.100.4",
    )
    malformed = _request(
        remote_addr="10.0.0.2",
        forwarded_for="198.51.100.4, definitely-not-an-ip",
    )

    assert get_trusted_client_ip(untrusted_peer) == "203.0.113.8"
    assert get_trusted_client_ip(malformed) == "10.0.0.2"



@override_settings(AUTH_TRUST_PROXY_HEADERS=False, AUTH_TRUSTED_PROXY_CIDRS=())
def test_authentication_throttles_ignore_forged_forwarding_headers():
    from apps.lib.throttle import PasswordLoginRateThrottle

    throttle = PasswordLoginRateThrottle()
    first = _request(remote_addr="203.0.113.8", forwarded_for="198.51.100.4")
    forged = _request(remote_addr="203.0.113.8", forwarded_for="198.51.100.5")
    assert throttle.get_ident(first) == "203.0.113.8"
    assert throttle.get_cache_key(first, None) == throttle.get_cache_key(forged, None)


@override_settings(AUTH_TRUST_PROXY_HEADERS=True, AUTH_TRUSTED_PROXY_CIDRS=("10.0.0.2/32",))
def test_authentication_throttles_distinguish_clients_of_a_trusted_proxy():
    from apps.lib.throttle import PasswordLoginRateThrottle

    throttle = PasswordLoginRateThrottle()
    first = _request(remote_addr="10.0.0.2", forwarded_for="192.0.2.99, 198.51.100.4")
    second = _request(remote_addr="10.0.0.2", forwarded_for="198.51.100.5")
    assert throttle.get_ident(first) == "198.51.100.4"
    assert throttle.get_cache_key(first, None) != throttle.get_cache_key(second, None)
