from collections.abc import Iterable
from typing import Any

from django.db import transaction

from apps.lib.loggers import AppLogger
from apps.products.models import Product, ProductImage
from apps.products.tasks import generate_product_image_thumbnail


@transaction.atomic
def create_product_service(*, validated_data: dict[str, Any]) -> Product:
    """Create a product from data already validated by the input serializer."""
    return Product.objects.create(**validated_data)


@transaction.atomic
def update_product_service(
    *, product: Product, validated_data: dict[str, Any]
) -> Product:
    """Update a product in one transaction from serializer-validated data."""
    for field, value in validated_data.items():
        setattr(product, field, value)
    product.save()
    return product


@transaction.atomic
def delete_product_service(*, product: Product) -> None:
    """Delete a product and schedule uploaded-file removal after commit."""
    image_names = [
        field.name
        for image in product.images.all()
        for field in (image.image, image.thumbnail)
        if field.name
    ]
    storage = ProductImage._meta.get_field("image").storage
    product.delete()
    transaction.on_commit(lambda: _delete_files(storage, image_names))


@transaction.atomic
def create_product_image_service(
    *,
    product: Product,
    image_file: Any,
    is_primary: bool,
    display_order: int,
) -> ProductImage:
    """Create an image while atomically enforcing one primary image per product."""
    if is_primary:
        Product.objects.select_for_update().get(pk=product.pk)
        ProductImage.objects.filter(product=product, is_primary=True).update(
            is_primary=False
        )

    product_image = ProductImage.objects.create(
        product=product,
        image=image_file,
        is_primary=is_primary,
        display_order=display_order,
    )
    transaction.on_commit(lambda: _enqueue_thumbnail(product_image.id))
    return product_image


@transaction.atomic
def delete_product_image_service(*, product_image: ProductImage) -> None:
    """Delete an image record and delete its object-storage file after commit."""
    image_names = [
        field.name
        for field in (product_image.image, product_image.thumbnail)
        if field.name
    ]
    storage = product_image.image.storage
    product_image.delete()
    if image_names:
        transaction.on_commit(lambda: _delete_files(storage, image_names))


def _delete_files(storage: Any, image_names: Iterable[str]) -> None:
    for image_name in image_names:
        try:
            storage.delete(image_name)
        except Exception:
            AppLogger.log_system_error(
                msg=f"Failed to delete product image from storage: {image_name}",
                include_traceback=True,
            )


def _enqueue_thumbnail(product_image_id: int) -> None:
    """Keep a broker outage from turning a committed upload into an HTTP failure."""
    try:
        generate_product_image_thumbnail.delay(product_image_id)
    except Exception:
        AppLogger.log_system_error(
            msg=f"Failed to queue thumbnail for product image {product_image_id}",
            include_traceback=True,
        )
