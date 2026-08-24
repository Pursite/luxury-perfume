from io import BytesIO

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.lib.loggers import AppLogger
from apps.lib.tasks import CorrelatedTask
from apps.products.models import ProductImage


THUMBNAIL_SIZE = (600, 600)


@shared_task(
    autoretry_for=(OSError, UnidentifiedImageError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    base=CorrelatedTask,
)
def generate_product_image_thumbnail(product_image_id: int) -> None:
    """Generate a WebP thumbnail without delaying an image-upload response."""
    generated_thumbnail_name = None
    cleanup_attempted = False

    try:
        with transaction.atomic():
            try:
                product_image = ProductImage.objects.select_for_update().get(
                    pk=product_image_id
                )
            except ProductImage.DoesNotExist:
                return

            storage = product_image.thumbnail.storage
            current_thumbnail_name = product_image.thumbnail.name
            if current_thumbnail_name and storage.exists(current_thumbnail_name):
                return

            with product_image.image.open("rb") as image_file:
                image = Image.open(image_file)
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGB")
                image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

                output = BytesIO()
                image.save(output, format="WEBP", quality=82, method=6)

            thumbnail_field = ProductImage._meta.get_field("thumbnail")
            thumbnail_name = thumbnail_field.generate_filename(
                product_image,
                f"by-image-id/{product_image.id}/thumbnail.webp",
            )
            if storage.exists(thumbnail_name):
                if ProductImage.objects.exclude(pk=product_image.id).filter(
                    thumbnail=thumbnail_name
                ).exists():
                    raise OSError("Deterministic thumbnail name is already referenced")
                storage.delete(thumbnail_name)
                if storage.exists(thumbnail_name):
                    raise OSError("Deterministic thumbnail name remains unavailable")

            try:
                with transaction.atomic():
                    generated_thumbnail_name = storage.save(
                        thumbnail_name,
                        ContentFile(output.getvalue()),
                        max_length=thumbnail_field.max_length,
                    )
                    if generated_thumbnail_name != thumbnail_name:
                        raise OSError(
                            "Storage changed the deterministic thumbnail name"
                        )

                    product_image.thumbnail.name = generated_thumbnail_name
                    product_image.save(update_fields=["thumbnail", "updated_at"])
            except Exception:
                if generated_thumbnail_name:
                    cleanup_attempted = True
                    _delete_unreferenced_thumbnail(storage, generated_thumbnail_name)
                raise
    except Exception:
        if generated_thumbnail_name and not cleanup_attempted:
            _delete_thumbnail_after_transaction_failure(
                product_image_id=product_image_id,
                storage=storage,
                thumbnail_name=generated_thumbnail_name,
            )
        AppLogger.log_system_error(
            msg="product_image.thumbnail_generation_failed",
            include_traceback=True,
        )
        raise


def _delete_unreferenced_thumbnail(storage, thumbnail_name: str) -> None:
    try:
        _delete_thumbnail_if_unreferenced(storage, thumbnail_name)
    except Exception:
        AppLogger.log_system_error(
            msg="product_image.thumbnail_cleanup_failed",
            include_traceback=True,
        )


def _delete_thumbnail_after_transaction_failure(
    *,
    product_image_id: int,
    storage,
    thumbnail_name: str,
) -> None:
    try:
        with transaction.atomic():
            try:
                ProductImage.objects.select_for_update().get(pk=product_image_id)
            except ProductImage.DoesNotExist:
                pass
            _delete_thumbnail_if_unreferenced(storage, thumbnail_name)
    except Exception:
        AppLogger.log_system_error(
            msg="product_image.thumbnail_cleanup_failed",
            include_traceback=True,
        )


def _delete_thumbnail_if_unreferenced(storage, thumbnail_name: str) -> None:
    if ProductImage.objects.filter(thumbnail=thumbnail_name).exists():
        return
    storage.delete(thumbnail_name)
