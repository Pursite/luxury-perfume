import pytest
from django.core.cache import caches
from django.db import transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.products.cache import (
    CACHE_VERSION_KEY,
    get_catalog_cache_version,
    invalidate_product_api_cache,
    product_list_cache_key,
)
from apps.products.models import ProductFragranceNote
from apps.products.services import update_product_service
from apps.products.tests.factories import FragranceNoteFactory, ProductFactory


@pytest.mark.django_db
def test_public_detail_response_is_reused_until_namespace_invalidation(api_client):
    product = ProductFactory(name="Cached name")
    url = reverse(
        "apps.products:product-detail",
        kwargs={"product_uuid": product.uuid},
    )

    first_response = api_client.get(url)
    ProductFactory._meta.model.objects.filter(pk=product.pk).update(name="Database name")
    cached_response = api_client.get(url)
    invalidate_product_api_cache()
    refreshed_response = api_client.get(url)

    assert first_response.status_code == status.HTTP_200_OK
    assert cached_response.data["name"] == "Cached name"
    assert refreshed_response.data["name"] == "Database name"


@pytest.mark.django_db
def test_current_catalog_does_not_reuse_pre_ordered_note_cache_entries(api_client):
    product = ProductFactory(name="Current fragrance")
    legacy_key = f"products:v1:detail:{product.uuid}"
    caches["default"].set(legacy_key, {"name": "Obsolete cached fragrance"})
    url = reverse(
        "apps.products:product-detail",
        kwargs={"product_uuid": product.uuid},
    )

    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Current fragrance"


def test_product_list_cache_key_is_independent_of_query_order():
    factory = APIRequestFactory()
    first = Request(
        factory.get(
            "/api/v1/products/",
            [("brand", "2"), ("brand", "1"), ("search", "red")],
        )
    )
    second = Request(
        factory.get(
            "/api/v1/products/",
            [("search", "red"), ("brand", "1"), ("brand", "2")],
        )
    )

    assert product_list_cache_key(first) == product_list_cache_key(second)


def test_invalid_catalog_cache_version_is_repaired():
    caches["default"].set(CACHE_VERSION_KEY, "not-an-integer")

    assert get_catalog_cache_version() == 1
    assert caches["default"].get(CACHE_VERSION_KEY) == 1


@pytest.mark.django_db(transaction=True)
def test_cache_invalidation_runs_after_commit_but_not_after_rollback():
    product = ProductFactory(name="Original")
    initial_version = get_catalog_cache_version()

    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            product.name = "Rolled back"
            product.save(update_fields=["name"])
            raise RuntimeError("force rollback")

    assert get_catalog_cache_version() == initial_version
    product.refresh_from_db()
    assert product.name == "Original"

    with transaction.atomic():
        product.name = "Committed"
        product.save(update_fields=["name"])

    assert get_catalog_cache_version() == initial_version + 1


@pytest.mark.django_db(transaction=True)
def test_fragrance_note_relation_changes_invalidate_catalog_cache():
    product = ProductFactory()
    note = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    initial_version = get_catalog_cache_version()

    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=note,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )

    assert get_catalog_cache_version() == initial_version + 1


@pytest.mark.django_db(transaction=True)
def test_note_only_service_update_invalidates_a_cached_detail(api_client):
    product = ProductFactory()
    note = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    url = reverse(
        "apps.products:product-detail",
        kwargs={"product_uuid": product.uuid},
    )
    first_response = api_client.get(url)

    update_product_service(product=product, validated_data={"top_notes": [note]})
    refreshed_response = api_client.get(url)

    assert first_response.data["top_notes"] == []
    assert [item["uuid"] for item in refreshed_response.data["top_notes"]] == [
        str(note.id)
    ]


@pytest.mark.django_db(transaction=True)
def test_fragrance_note_rename_invalidates_catalog_cache():
    note = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    initial_version = get_catalog_cache_version()

    note.name = "Calabrian Bergamot"
    note.save(update_fields=["name", "updated_at"])

    assert get_catalog_cache_version() == initial_version + 1
