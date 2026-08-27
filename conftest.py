"""Shared pytest fixtures and cross-test isolation."""

import pytest
from django.core.cache import caches
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Return an un-authenticated DRF API client."""
    return APIClient(HTTP_ORIGIN="http://testserver")


@pytest.fixture(autouse=True)
def clear_all_configured_caches(settings):
    """Prevent state leaking through any configured cache alias."""
    configured_caches = [caches[alias] for alias in settings.CACHES]
    for cache_backend in configured_caches:
        cache_backend.clear()

    yield

    for cache_backend in configured_caches:
        cache_backend.clear()
