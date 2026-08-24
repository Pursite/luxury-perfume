import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from PIL import Image, UnidentifiedImageError

from apps.products.models import ProductImage
from apps.products.tasks import generate_product_image_thumbnail
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = pytest.mark.django_db


def test_thumbnail_task_creates_webp_derivative():
    product_image = ProductImageFactory()

    generate_product_image_thumbnail(product_image.id)

    product_image.refresh_from_db()
    assert product_image.thumbnail.name == (
        f"products/thumbnails/by-image-id/{product_image.id}/thumbnail.webp"
    )
    assert product_image.thumbnail.storage.exists(product_image.thumbnail.name)


def test_thumbnail_task_redelivery_reuses_current_thumbnail():
    product_image = ProductImageFactory()

    generate_product_image_thumbnail.run.__wrapped__(product_image.id)
    product_image.refresh_from_db()
    first_thumbnail_name = product_image.thumbnail.name

    generate_product_image_thumbnail.run.__wrapped__(product_image.id)
    product_image.refresh_from_db()
    _, thumbnail_files = product_image.thumbnail.storage.listdir(
        f"products/thumbnails/by-image-id/{product_image.id}"
    )

    assert product_image.thumbnail.name == first_thumbnail_name
    assert thumbnail_files == ["thumbnail.webp"]


def test_thumbnail_task_retains_existing_legacy_thumbnail():
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    legacy_thumbnail_name = "products/thumbnails/example-thumbnail.webp"
    storage.save(legacy_thumbnail_name, ContentFile(b"valid legacy thumbnail"))
    product_image.thumbnail.name = legacy_thumbnail_name
    product_image.save(update_fields=["thumbnail", "updated_at"])

    generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    with storage.open(legacy_thumbnail_name, "rb") as legacy_thumbnail:
        legacy_content = legacy_thumbnail.read()

    assert product_image.thumbnail.name == legacy_thumbnail_name
    assert legacy_content == b"valid legacy thumbnail"


def test_new_thumbnail_namespace_does_not_collide_with_legacy_thumbnail_key():
    product_image = ProductImageFactory()
    legacy_product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    legacy_thumbnail_name = (
        f"products/thumbnails/{product_image.id}-thumbnail.webp"
    )
    storage.save(legacy_thumbnail_name, ContentFile(b"valid legacy thumbnail"))
    legacy_product_image.thumbnail.name = legacy_thumbnail_name
    legacy_product_image.save(update_fields=["thumbnail", "updated_at"])

    generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    legacy_product_image.refresh_from_db()
    with storage.open(legacy_thumbnail_name, "rb") as legacy_thumbnail:
        legacy_content = legacy_thumbnail.read()

    assert product_image.thumbnail.name == (
        f"products/thumbnails/by-image-id/{product_image.id}/thumbnail.webp"
    )
    assert storage.exists(product_image.thumbnail.name)
    assert legacy_product_image.thumbnail.name == legacy_thumbnail_name
    assert legacy_content == b"valid legacy thumbnail"


def test_thumbnail_task_replaces_stale_deterministic_worker_loss_file():
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    thumbnail_name = (
        f"products/thumbnails/by-image-id/{product_image.id}/thumbnail.webp"
    )
    storage.save(thumbnail_name, ContentFile(b"partial worker-loss write"))

    generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    _, thumbnail_files = storage.listdir(
        f"products/thumbnails/by-image-id/{product_image.id}"
    )
    with storage.open(product_image.thumbnail.name, "rb") as thumbnail_file:
        generated_image = Image.open(thumbnail_file)
        generated_image.load()

    assert product_image.thumbnail.name == thumbnail_name
    assert thumbnail_files == ["thumbnail.webp"]
    assert generated_image.format == "WEBP"


def test_thumbnail_task_rejects_and_cleans_alternative_storage_name(mocker):
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    storage_save = storage.save

    def save_under_alternative_name(name, content, max_length=None):
        return storage_save(
            "products/thumbnails/unexpected-alternative.webp",
            content,
            max_length=max_length,
        )

    mocker.patch.object(storage, "save", side_effect=save_under_alternative_name)

    with pytest.raises(OSError, match="deterministic thumbnail name"):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    assert not product_image.thumbnail
    assert storage.exists("products/thumbnails/unexpected-alternative.webp") is False


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
):
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    mocker.patch.object(
        ProductImage,
        "save",
        side_effect=RuntimeError("database unavailable"),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    _, thumbnail_files = storage.listdir("products/thumbnails")
    assert thumbnail_files == []


@pytest.mark.django_db(transaction=True)
def test_thumbnail_commit_failure_does_not_leave_orphan_file(mocker):
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    original_commit = connection.commit
    commit_calls = 0

    def fail_first_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise DatabaseError("simulated commit failure")
        return original_commit()

    mocker.patch.object(connection, "commit", side_effect=fail_first_commit)

    with pytest.raises(DatabaseError, match="commit failure"):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    product_image.refresh_from_db()
    assert not product_image.thumbnail
    assert storage.exists(
        f"products/thumbnails/by-image-id/{product_image.id}/thumbnail.webp"
    ) is False


def test_thumbnail_cleanup_failure_is_logged_without_masking_database_error(
    mocker,
):
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    mocker.patch.object(
        ProductImage,
        "save",
        side_effect=RuntimeError("database unavailable"),
    )
    mocker.patch.object(storage, "delete", side_effect=OSError("storage unavailable"))
    error_log = mocker.patch("apps.products.tasks.AppLogger.log_system_error")

    with pytest.raises(RuntimeError, match="database unavailable"):
        generate_product_image_thumbnail.run.__wrapped__(product_image.id)

    assert storage.exists(
        f"products/thumbnails/by-image-id/{product_image.id}/thumbnail.webp"
    )
    error_log.assert_any_call(
        msg="product_image.thumbnail_cleanup_failed",
        include_traceback=True,
    )
    error_log.assert_any_call(
        msg="product_image.thumbnail_generation_failed",
        include_traceback=True,
    )
