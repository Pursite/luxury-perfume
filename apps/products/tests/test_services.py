import pytest
from django.core.files.base import ContentFile
from django.db import transaction

from apps.products.models import Product, ProductImage
from apps.products.services import (
    _enqueue_thumbnail,
    delete_product_image_service,
    delete_product_service,
    update_product_service,
)
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = pytest.mark.django_db


def test_product_update_rolls_back_when_save_fails_after_database_write(mocker):
    product = ProductFactory(name="Original")
    original_save = product.save

    def save_then_fail(*args, **kwargs):
        original_save(*args, **kwargs)
        raise RuntimeError("simulated post-write failure")

    mocker.patch.object(product, "save", side_effect=save_then_fail)

    with pytest.raises(RuntimeError, match="post-write failure"):
        update_product_service(
            product=product,
            validated_data={"name": "Must roll back"},
        )

    product.refresh_from_db()
    assert product.name == "Original"


def test_image_delete_removes_original_and_thumbnail_after_commit(
    django_capture_on_commit_callbacks,
):
    product_image = ProductImageFactory()
    product_image.thumbnail.save(
        "existing-thumbnail.webp",
        ContentFile(b"thumbnail"),
        save=True,
    )
    storage = product_image.image.storage
    image_name = product_image.image.name
    thumbnail_name = product_image.thumbnail.name

    with django_capture_on_commit_callbacks(execute=True):
        delete_product_image_service(product_image=product_image)

    assert not ProductImage.objects.filter(pk=product_image.pk).exists()
    assert storage.exists(image_name) is False
    assert storage.exists(thumbnail_name) is False


def test_product_delete_removes_all_image_files_after_commit(
    django_capture_on_commit_callbacks,
):
    product = ProductFactory()
    first = ProductImageFactory(product=product)
    second = ProductImageFactory(product=product)
    storage = first.image.storage
    names = [first.image.name, second.image.name]

    with django_capture_on_commit_callbacks(execute=True):
        delete_product_service(product=product)

    assert not Product.objects.filter(pk=product.pk).exists()
    assert all(storage.exists(name) is False for name in names)


def test_rolled_back_image_delete_preserves_row_and_file():
    product_image = ProductImageFactory()
    storage = product_image.image.storage
    image_name = product_image.image.name
    image_id = product_image.pk

    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            delete_product_image_service(product_image=product_image)
            raise RuntimeError("force rollback")

    assert ProductImage.objects.filter(pk=image_id).exists()
    assert storage.exists(image_name)


def test_storage_cleanup_failure_is_contained_and_reported(
    django_capture_on_commit_callbacks,
    mocker,
):
    product_image = ProductImageFactory()
    storage = product_image.image.storage
    mocker.patch.object(
        storage,
        "delete",
        side_effect=OSError("storage unavailable"),
    )
    error_log = mocker.patch("apps.products.services.AppLogger.log_system_error")

    with django_capture_on_commit_callbacks(execute=True):
        delete_product_image_service(product_image=product_image)

    assert not ProductImage.objects.filter(pk=product_image.pk).exists()
    error_log.assert_called_once()


def test_thumbnail_enqueue_failure_does_not_reverse_committed_upload(mocker):
    delay = mocker.patch(
        "apps.products.services.generate_product_image_thumbnail.delay",
        side_effect=OSError("broker unavailable"),
    )
    error_log = mocker.patch("apps.products.services.AppLogger.log_system_error")

    _enqueue_thumbnail(123)

    delay.assert_called_once_with(123)
    error_log.assert_called_once()

