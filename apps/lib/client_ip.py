"""Trusted client-IP extraction shared by security-sensitive entry points."""

from ipaddress import ip_address, ip_network

from django.conf import settings


MAX_FORWARDED_FOR_LENGTH = 1024
MAX_FORWARDED_HOPS = 10


def _parse_ip(value):
    try:
        return ip_address(value.strip())
    except (AttributeError, ValueError):
        return None


def get_trusted_client_ip(request):
    """Return the first untrusted hop without accepting client-spoofed headers."""
    peer = _parse_ip(request.META.get("REMOTE_ADDR"))
    if peer is None:
        return None
    peer_text = str(peer)
    if not getattr(settings, "PAYMENT_TRUST_PROXY_HEADERS", False):
        return peer_text

    try:
        trusted_networks = tuple(
            ip_network(cidr, strict=False)
            for cidr in getattr(settings, "PAYMENT_TRUSTED_PROXY_CIDRS", ())
        )
    except ValueError:
        return peer_text
    if not any(peer in network for network in trusted_networks):
        return peer_text

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not forwarded or len(forwarded) > MAX_FORWARDED_FOR_LENGTH:
        return peer_text
    raw_hops = forwarded.split(",")
    if len(raw_hops) > MAX_FORWARDED_HOPS:
        return peer_text
    hops = [_parse_ip(value) for value in raw_hops]
    if any(hop is None for hop in hops):
        return peer_text

    candidate = peer
    for hop in reversed(hops):
        if not any(candidate in network for network in trusted_networks):
            break
        candidate = hop
    return str(candidate)
