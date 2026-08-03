from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, transaction

from apps.products.cache import get_catalog_cache_version
from apps.products.models import Product, ProductImage
from apps.products.services import create_product_image_service
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def test_postgresql_reports_named_product_constraints():
    invalid_product = ProductFactory.build(
        price=Decimal("100.00"),
        discount_price=Decimal("100.00"),
    )

    with pytest.raises(IntegrityError) as discount_error:
        with transaction.atomic():
            invalid_product.save(force_insert=True)

    assert (
        discount_error.value.__cause__.diag.constraint_name
        == "product_discount_lower_than_price"
    )

    product = ProductFactory()
    ProductImageFactory(product=product, is_primary=True)
    with pytest.raises(IntegrityError) as primary_error:
        with transaction.atomic():
            ProductImageFactory(product=product, is_primary=True)

    assert (
        primary_error.value.__cause__.diag.constraint_name
        == "one_primary_image_per_product"
    )


def test_postgresql_rollback_discards_rows_and_on_commit_cache_invalidation():
    initial_version = get_catalog_cache_version()
    sku = "ROLLBACK-PG-001"

    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            ProductFactory(sku=sku)
            raise RuntimeError("force rollback")

    assert not Product.objects.filter(sku=sku).exists()
    assert get_catalog_cache_version() == initial_version


def test_primary_image_updates_are_serialized_by_real_row_lock(mocker):
    product = ProductFactory()
    ready = Barrier(2)
    mocker.patch(
        "apps.products.services.generate_product_image_thumbnail.delay"
    )

    def create_primary(name):
        close_old_connections()
        try:
            thread_product = Product.objects.get(pk=product.pk)
            ready.wait(timeout=10)
            return create_product_image_service(
                product=thread_product,
                image_file=SimpleUploadedFile(
                    name,
                    b"threaded-image-content",
                    content_type="image/jpeg",
                ),
                is_primary=True,
                display_order=0,
            ).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create_primary, "first.jpg"),
            executor.submit(create_primary, "second.jpg"),
        ]
        created_ids = [future.result(timeout=20) for future in futures]

    assert len(set(created_ids)) == 2
    assert ProductImage.objects.filter(product=product).count() == 2
    assert ProductImage.objects.filter(
        product=product,
        is_primary=True,
    ).count() == 1

