from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import UnidentifiedImageError

from apps.products.models import ProductImage
from apps.products.tasks import generate_product_image_thumbnail
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = pytest.mark.django_db


def test_thumbnail_task_creates_webp_derivative():
    product_image = ProductImageFactory()

    generate_product_image_thumbnail(product_image.id)

    product_image.refresh_from_db()
    assert product_image.thumbnail.name.endswith("-thumbnail.webp")
    assert product_image.thumbnail.storage.exists(product_image.thumbnail.name)


def test_thumbnail_task_ignores_missing_database_row():
    assert generate_product_image_thumbnail(999999) is None


def test_thumbnail_task_propagates_corrupt_image_failure():
    product_image = ProductImage.objects.create(
        product=ProductFactory(),
        image=SimpleUploadedFile(
            "corrupt.jpg",
            b"not an image",
            content_type="image/jpeg",
        ),
    )

    with pytest.raises(UnidentifiedImageError):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    assert not product_image.thumbnail


def test_thumbnail_database_failure_does_not_leave_orphan_file(
    mocker,
    settings,
):
    product_image = ProductImageFactory()
    mocker.patch.object(
        ProductImage,
        "save",
        side_effect=RuntimeError("database unavailable"),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    thumbnails = list(
        Path(settings.MEDIA_ROOT).glob("products/thumbnails/*-thumbnail.webp")
    )
    assert thumbnails == []

