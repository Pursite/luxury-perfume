from hashlib import sha256
from urllib.parse import urlencode

from apps.lib.cache import RedisCacheService


CACHE_VERSION_KEY = "products:fragrance-catalog:version"
CACHE_VERSION_TIMEOUT = 7 * 24 * 60 * 60
PRODUCT_LIST_CACHE_TTL = 60
PRODUCT_DETAIL_CACHE_TTL = 5 * 60


def get_catalog_cache_version() -> int:
    version = RedisCacheService.get(CACHE_VERSION_KEY)
    if version is None:
        RedisCacheService.set(CACHE_VERSION_KEY, 1, timeout=CACHE_VERSION_TIMEOUT)
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        RedisCacheService.set(CACHE_VERSION_KEY, 1, timeout=CACHE_VERSION_TIMEOUT)
        return 1


def invalidate_product_api_cache() -> None:
    """Advance a namespace version instead of deleting every paginated cache key."""
    RedisCacheService.incr(CACHE_VERSION_KEY, timeout=CACHE_VERSION_TIMEOUT)


def product_list_cache_key(request) -> str:
    query_items = [
        (key, value)
        for key, values in request.query_params.lists()
        for value in sorted(values)
    ]
    canonical_query = urlencode(sorted(query_items), doseq=True)
    fingerprint = sha256(
        f"{request.get_host()}|{request.path}|{canonical_query}".encode()
    ).hexdigest()
    return f"products:v{get_catalog_cache_version()}:list:{fingerprint}"


def product_detail_cache_key(*, product_uuid) -> str:
    return f"products:v{get_catalog_cache_version()}:detail:{product_uuid}"
