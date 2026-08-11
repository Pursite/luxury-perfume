import pytest
from django.core.files.base import ContentFile
from django.db import transaction

from apps.products.models import Product, ProductFragranceNote, ProductImage
from apps.products.services import (
    _enqueue_thumbnail,
    create_product_service,
    delete_product_image_service,
    delete_product_service,
    update_product_service,
)
from apps.products.tests.factories import (
    BrandFactory,
    CategoryFactory,
    FragranceNoteFactory,
    ProductFactory,
    ProductImageFactory,
)


pytestmark = pytest.mark.django_db


def _ordered_note_names(product, layer):
    return list(
        product.fragrance_note_links.filter(layer=layer)
        .order_by("position")
        .values_list("fragrance_note__name", flat=True)
    )


def test_product_create_sets_fragrance_note_layers_atomically():
    category = CategoryFactory()
    brand = BrandFactory()
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    lemon = FragranceNoteFactory(name="Lemon", slug="lemon")
    jasmine = FragranceNoteFactory(name="Jasmine", slug="jasmine")
    musk = FragranceNoteFactory(name="Musk", slug="musk")

    product = create_product_service(
        validated_data={
            "category": category,
            "brand": brand,
            "name": "Aurora Eau de Parfum",
            "slug": "aurora-eau-de-parfum",
            "sku": "AUR-SERVICE-001",
            "description": "A luminous floral fragrance.",
            "price": "150.00",
            "discount_price": "120.00",
            "stock": 10,
            "concentration": "eau_de_parfum",
            "target_audience": "unisex",
            "fragrance_family": "floral",
            "volume_ml": 100,
            "top_notes": [lemon, bergamot],
            "middle_notes": [jasmine],
            "base_notes": [musk],
        }
    )

    assert _ordered_note_names(product, ProductFragranceNote.Layer.TOP) == [
        "Lemon",
        "Bergamot",
    ]
    assert _ordered_note_names(product, ProductFragranceNote.Layer.MIDDLE) == [
        "Jasmine"
    ]
    assert _ordered_note_names(product, ProductFragranceNote.Layer.BASE) == ["Musk"]
    assert list(
        product.fragrance_note_links.filter(
            layer=ProductFragranceNote.Layer.TOP
        ).values_list("position", flat=True)
    ) == [1, 2]


def test_product_update_preserves_omitted_notes_and_clears_explicit_empty_layer():
    product = ProductFactory()
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    jasmine = FragranceNoteFactory(name="Jasmine", slug="jasmine")
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=bergamot,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=jasmine,
        layer=ProductFragranceNote.Layer.MIDDLE,
        position=1,
    )

    update_product_service(
        product=product,
        validated_data={"name": "Updated fragrance", "top_notes": []},
    )

    assert product.name == "Updated fragrance"
    assert _ordered_note_names(product, ProductFragranceNote.Layer.TOP) == []
    assert _ordered_note_names(product, ProductFragranceNote.Layer.MIDDLE) == [
        "Jasmine"
    ]


def test_product_update_replaces_a_layer_in_the_submitted_order():
    product = ProductFactory()
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    lemon = FragranceNoteFactory(name="Lemon", slug="lemon")
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=bergamot,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )

    update_product_service(
        product=product,
        validated_data={"top_notes": [lemon, bergamot]},
    )

    assert _ordered_note_names(product, ProductFragranceNote.Layer.TOP) == [
        "Lemon",
        "Bergamot",
    ]


def test_product_update_rolls_back_when_save_fails_after_database_write(mocker):
    product = ProductFactory(name="Original")
    original_save = Product.save

    def save_then_fail(instance, *args, **kwargs):
        original_save(instance, *args, **kwargs)
        raise RuntimeError("simulated post-write failure")

    mocker.patch.object(Product, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="post-write failure"):
        update_product_service(
            product=product,
            validated_data={"name": "Must roll back"},
        )

    product.refresh_from_db()
    assert product.name == "Original"


def test_product_update_rolls_back_scalar_and_note_replacement_together(mocker):
    product = ProductFactory(name="Original")
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    lemon = FragranceNoteFactory(name="Lemon", slug="lemon")
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=bergamot,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )
    original_bulk_create = ProductFragranceNote.objects.bulk_create

    def create_then_fail(objects, *args, **kwargs):
        original_bulk_create(objects, *args, **kwargs)
        raise RuntimeError("simulated note write failure")

    mocker.patch.object(
        ProductFragranceNote.objects,
        "bulk_create",
        side_effect=create_then_fail,
    )

    with pytest.raises(RuntimeError, match="note write failure"):
        update_product_service(
            product=product,
            validated_data={"name": "Must roll back", "top_notes": [lemon]},
        )

    product.refresh_from_db()
    assert product.name == "Original"
    assert _ordered_note_names(product, ProductFragranceNote.Layer.TOP) == [
        "Bergamot"
    ]


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
