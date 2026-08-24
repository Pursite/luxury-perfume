from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.db import transaction
from django.db.models import Q

from apps.lib.loggers import AppLogger
from apps.products.models import FragranceNote, Product, ProductFragranceNote, ProductImage
from apps.products.tasks import generate_product_image_thumbnail


FRAGRANCE_NOTE_LAYERS = {
    "top_notes": ProductFragranceNote.Layer.TOP,
    "middle_notes": ProductFragranceNote.Layer.MIDDLE,
    "base_notes": ProductFragranceNote.Layer.BASE,
}


def _split_fragrance_notes(validated_data: dict[str, Any]):
    scalar_data = dict(validated_data)
    fragrance_notes = {
        field: scalar_data.pop(field)
        for field in FRAGRANCE_NOTE_LAYERS
        if field in scalar_data
    }
    return scalar_data, fragrance_notes


def _replace_fragrance_note_layer(
    *,
    product: Product,
    layer: str,
    notes: Iterable[FragranceNote],
) -> None:
    ProductFragranceNote.objects.filter(product=product, layer=layer).delete()
    ProductFragranceNote.objects.bulk_create([
        ProductFragranceNote(
            product=product,
            fragrance_note=note,
            layer=layer,
            position=position,
        )
        for position, note in enumerate(notes, start=1)
    ])


def _clear_fragrance_note_prefetch(product: Product) -> None:
    for attribute in (
        "_ordered_fragrance_note_links",
        "_serialized_fragrance_note_links",
    ):
        if hasattr(product, attribute):
            delattr(product, attribute)
    prefetched_objects = getattr(product, "_prefetched_objects_cache", {})
    prefetched_objects.pop("fragrance_note_links", None)
    prefetched_objects.pop("fragrance_notes", None)


@transaction.atomic
def create_product_service(*, validated_data: dict[str, Any]) -> Product:
    """Create a product from data already validated by the input serializer."""
    scalar_data, fragrance_notes = _split_fragrance_notes(validated_data)
    product = Product.objects.create(**scalar_data)
    for field, notes in fragrance_notes.items():
        _replace_fragrance_note_layer(
            product=product,
            layer=FRAGRANCE_NOTE_LAYERS[field],
            notes=notes,
        )
    _clear_fragrance_note_prefetch(product)
    return product


@transaction.atomic
def update_product_service(
    *, product: Product, validated_data: dict[str, Any]
) -> Product:
    """Update a product in one transaction from serializer-validated data."""
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    scalar_data, fragrance_notes = _split_fragrance_notes(validated_data)
    for field, value in scalar_data.items():
        setattr(locked_product, field, value)
    locked_product.save()
    for field, notes in fragrance_notes.items():
        _replace_fragrance_note_layer(
            product=locked_product,
            layer=FRAGRANCE_NOTE_LAYERS[field],
            notes=notes,
        )
    product.refresh_from_db()
    _clear_fragrance_note_prefetch(product)
    return product


@transaction.atomic
def delete_products_service(*, product_ids: Iterable[int]) -> int:
    """Delete products atomically and remove their uploaded files after commit."""
    requested_ids = sorted({product_id for product_id in product_ids if product_id})
    if not requested_ids:
        return 0

    locked_products = list(
        Product.objects.select_for_update()
        .filter(pk__in=requested_ids)
        .order_by("pk")
    )
    locked_product_ids = [product.pk for product in locked_products]
    if not locked_product_ids:
        return 0

    product_images = list(
        ProductImage.objects.select_for_update()
        .filter(product_id__in=locked_product_ids)
        .order_by("pk")
    )
    image_names = [
        field.name
        for image in product_images
        for field in (image.image, image.thumbnail)
        if field.name
    ]
    storage = ProductImage._meta.get_field("image").storage
    Product.objects.filter(pk__in=locked_product_ids).delete()
    if image_names:
        transaction.on_commit(lambda: _delete_files(storage, image_names))
    return len(locked_product_ids)


def delete_product_service(*, product: Product) -> bool:
    """Delete one product and report whether its resolved row still existed."""
    return delete_products_service(product_ids=[product.pk]) == 1


def create_product_image_service(
    *,
    product: Product,
    image_file: Any,
    is_primary: bool,
    display_order: int,
) -> ProductImage:
    """Create an image while atomically enforcing one primary image per product."""
    return _create_product_image_service(
        product=product,
        image_file=image_file,
        is_primary=is_primary,
        display_order=display_order,
        durable=True,
    )


def create_product_image_in_transaction_service(
    *,
    product: Product,
    image_file: Any,
    is_primary: bool,
    display_order: int,
) -> ProductImage:
    """Create an image inside a transaction owned by the caller."""
    return _create_product_image_service(
        product=product,
        image_file=image_file,
        is_primary=is_primary,
        display_order=display_order,
        durable=False,
    )


def _create_product_image_service(
    *,
    product: Product,
    image_file: Any,
    is_primary: bool,
    display_order: int,
    durable: bool,
) -> ProductImage:
    product_image = ProductImage(
        product=product,
        image=image_file,
        is_primary=is_primary,
        display_order=display_order,
    )
    product_image.image.name = _unique_original_name(product_image.image.name)
    image_was_committed = product_image.image._committed

    try:
        with transaction.atomic(durable=durable):
            if is_primary:
                Product.objects.select_for_update().get(pk=product.pk)
                ProductImage.objects.filter(product=product, is_primary=True).update(
                    is_primary=False
                )

            product_image.save(force_insert=True)
            transaction.on_commit(lambda: _enqueue_thumbnail(product_image.id))
    except Exception:
        if not image_was_committed and product_image.image._committed:
            cleanup_product_image_original_after_rollback(product_image)
        raise

    return product_image


def _unique_original_name(original_name: str) -> str:
    """Return a collision-resistant key while preserving the validated suffix."""
    return f"{uuid4().hex}{Path(original_name).suffix.lower()}"


def cleanup_product_image_original_after_rollback(
    product_image: ProductImage,
) -> None:
    image_name = product_image.image.name
    if not image_name:
        return

    try:
        if ProductImage.objects.filter(image=image_name).exists():
            return
        product_image.image.storage.delete(image_name)
    except Exception:
        AppLogger.log_system_error(
            msg="product_image.original_cleanup_failed",
            include_traceback=True,
        )


@transaction.atomic
def update_product_image_service(
    *,
    product_image: ProductImage,
    is_primary: bool,
    display_order: int,
) -> ProductImage:
    """Update editable image metadata while preserving primary-image integrity."""
    Product.objects.select_for_update().get(pk=product_image.product_id)
    locked_product_image = ProductImage.objects.select_for_update().get(
        pk=product_image.pk
    )
    if is_primary:
        ProductImage.objects.filter(
            product_id=locked_product_image.product_id,
            is_primary=True,
        ).exclude(pk=locked_product_image.pk).update(is_primary=False)
    locked_product_image.is_primary = is_primary
    locked_product_image.display_order = display_order
    locked_product_image.save(
        update_fields=["is_primary", "display_order", "updated_at"]
    )
    return locked_product_image


@transaction.atomic
def delete_product_image_service(*, product_image: ProductImage) -> bool:
    """Delete an image record and delete its object-storage file after commit."""
    try:
        locked_product_image = ProductImage.objects.select_for_update().get(
            pk=product_image.pk
        )
    except ProductImage.DoesNotExist:
        return False
    image_names = [
        field.name
        for field in (locked_product_image.image, locked_product_image.thumbnail)
        if field.name
    ]
    storage = locked_product_image.image.storage
    locked_product_image.delete()
    if image_names:
        transaction.on_commit(lambda: _delete_files(storage, image_names))
    return True


def _delete_files(storage: Any, image_names: Iterable[str]) -> None:
    candidate_names = tuple(dict.fromkeys(image_names))
    if not candidate_names:
        return

    try:
        referenced_names = set()
        references = ProductImage.objects.filter(
            Q(image__in=candidate_names) | Q(thumbnail__in=candidate_names)
        ).values_list("image", "thumbnail")
        for image_name, thumbnail_name in references:
            referenced_names.update(
                name
                for name in (image_name, thumbnail_name)
                if name in candidate_names
            )
    except Exception:
        AppLogger.log_system_error(
            msg="product_image.storage_reference_check_failed",
            include_traceback=True,
        )
        return

    for image_name in candidate_names:
        if image_name in referenced_names:
            continue
        try:
            storage.delete(image_name)
        except Exception:
            AppLogger.log_system_error(
                msg="product_image.storage_delete_failed",
                include_traceback=True,
            )


def _enqueue_thumbnail(product_image_id: int) -> None:
    """Keep a broker outage from turning a committed upload into an HTTP failure."""
    try:
        generate_product_image_thumbnail.delay(product_image_id)
    except Exception:
        AppLogger.log_system_error(
            msg="product_image.thumbnail_enqueue_failed",
            include_traceback=True,
        )
