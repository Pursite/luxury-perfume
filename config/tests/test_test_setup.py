from django.core.cache import caches


def test_cache_aliases_can_be_seeded_for_isolation_check():
    caches["default"].set("test-isolation-probe", "default")
    caches["security"].set("test-isolation-probe", "security")


def test_every_cache_alias_starts_empty():
    assert caches["default"].get("test-isolation-probe") is None
    assert caches["security"].get("test-isolation-probe") is None

