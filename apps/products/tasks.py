from io import BytesIO
from pathlib import Path

from celery import shared_task
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.lib.loggers import AppLogger
from apps.products.models import ProductImage


THUMBNAIL_SIZE = (600, 600)


@shared_task(
    autoretry_for=(OSError, UnidentifiedImageError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_product_image_thumbnail(product_image_id: int) -> None:
    """Generate a WebP thumbnail without delaying an image-upload response."""
    try:
        product_image = ProductImage.objects.get(pk=product_image_id)
    except ProductImage.DoesNotExist:
        return

    try:
        with product_image.image.open("rb") as image_file:
            image = Image.open(image_file)
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

            output = BytesIO()
            image.save(output, format="WEBP", quality=82, method=6)

        thumbnail_name = f"{Path(product_image.image.name).stem}-thumbnail.webp"
        product_image.thumbnail.save(
            thumbnail_name,
            ContentFile(output.getvalue()),
            save=False,
        )
        product_image.save(update_fields=["thumbnail", "updated_at"])
    except Exception:
        AppLogger.log_system_error(
            msg=f"Thumbnail generation failed for product image {product_image_id}",
            include_traceback=True,
        )
        raise
