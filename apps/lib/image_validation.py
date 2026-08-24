"""Reusable, content-aware validation for uploaded catalogue images."""

from pathlib import Path
import warnings

from django.utils.text import get_valid_filename
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


class RestrictedImageField(serializers.ImageField):
    """Preserve the declared upload MIME type for content validation."""

    def to_internal_value(self, data):
        declared_mime_type = getattr(data, "declared_mime_type", None)
        if declared_mime_type is None:
            declared_mime_type = getattr(data, "content_type", None)
        value = super().to_internal_value(data)
        value.declared_mime_type = declared_mime_type
        return value


class ValidatedCatalogueImageSerializer(serializers.Serializer):
    """Base serializer that accepts only safe JPEG, PNG, and WebP uploads."""

    allowed_mime_types = {
        "image/jpeg": ("JPEG", "jpg"),
        "image/png": ("PNG", "png"),
        "image/webp": ("WEBP", "webp"),
    }
    max_file_size = 5 * 1024 * 1024
    max_dimension = 6000
    image_field_name = "image"

    def validate_catalogue_image(self, value):
        if value.size > self.max_file_size:
            raise serializers.ValidationError("Image size must not exceed 5 MB.")

        declared_mime_type = getattr(value, "declared_mime_type", None)
        if declared_mime_type not in self.allowed_mime_types:
            raise serializers.ValidationError("Only JPEG, PNG, and WebP images are allowed.")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(value)
                image_format = image.format
                image.verify()

            value.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(value)
                width, height = image.size
                image.load()
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            UnidentifiedImageError,
        ) as exc:
            raise serializers.ValidationError(
                "Upload a valid, non-corrupted image file."
            ) from exc

        expected_format, extension = self.allowed_mime_types[declared_mime_type]
        if image_format != expected_format:
            raise serializers.ValidationError(
                "Image content does not match its MIME type."
            )
        if width > self.max_dimension or height > self.max_dimension:
            raise serializers.ValidationError(
                "Image dimensions must not exceed 6000 x 6000 pixels."
            )

        original_name = Path(str(value.name).replace("\\", "/")).name
        safe_stem = get_valid_filename(Path(original_name).stem).lstrip(".")[:80]
        value.name = f"{safe_stem or self.image_field_name}.{extension}"
        value.seek(0)
        return value
