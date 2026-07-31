from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError
from django.utils.text import get_valid_filename
from rest_framework import serializers

from apps.products.models import Brand, Category, Product, ProductImage


class CategorySummarySerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = Category
        fields = ("uuid", "name", "slug")


class BrandSummarySerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = Brand
        fields = ("uuid", "name", "slug", "country")


class ProductImageOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "thumbnail", "is_primary", "display_order")
        read_only_fields = fields


class RestrictedImageField(serializers.ImageField):
    """Keep the multipart MIME type so it can be checked after Pillow decodes it."""

    def to_internal_value(self, data):
        declared_mime_type = getattr(data, "content_type", None)
        value = super().to_internal_value(data)
        value.declared_mime_type = declared_mime_type
        return value


class ProductImageUploadInputSerializer(serializers.Serializer):
    allowed_mime_types = {
        "image/jpeg": ("JPEG", "jpg"),
        "image/png": ("PNG", "png"),
        "image/webp": ("WEBP", "webp"),
    }
    max_file_size = 5 * 1024 * 1024
    max_dimension = 6000

    image = RestrictedImageField()
    is_primary = serializers.BooleanField(default=False)
    display_order = serializers.IntegerField(min_value=0, default=0)

    def validate_image(self, value):
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
            raise serializers.ValidationError("Upload a valid, non-corrupted image file.") from exc

        expected_format, extension = self.allowed_mime_types[declared_mime_type]
        if image_format != expected_format:
            raise serializers.ValidationError("Image content does not match its MIME type.")
        if width > self.max_dimension or height > self.max_dimension:
            raise serializers.ValidationError("Image dimensions must not exceed 6000 x 6000 pixels.")

        original_name = Path(str(value.name).replace("\\", "/")).name
        safe_stem = get_valid_filename(Path(original_name).stem).lstrip(".")[:80]
        value.name = f"{safe_stem or 'product-image'}.{extension}"
        value.seek(0)
        return value


class ProductListOutputSerializer(serializers.ModelSerializer):
    category = CategorySummarySerializer(read_only=True)
    brand = BrandSummarySerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = (
            "uuid",
            "name",
            "slug",
            "sku",
            "price",
            "discount_price",
            "final_price",
            "stock",
            "abv",
            "volume_ml",
            "category",
            "brand",
            "primary_image",
            "is_featured",
            "created_at",
        )
        read_only_fields = fields

    def get_primary_image(self, product: Product):
        images = list(product.images.all())
        image = next((item for item in images if item.is_primary), None)
        image = image or (images[0] if images else None)
        if image is None:
            return None
        return ProductImageOutputSerializer(image, context=self.context).data


class ProductDetailOutputSerializer(serializers.ModelSerializer):
    category = CategorySummarySerializer(read_only=True)
    brand = BrandSummarySerializer(read_only=True)
    images = ProductImageOutputSerializer(many=True, read_only=True)
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = (
            "uuid",
            "name",
            "slug",
            "sku",
            "description",
            "price",
            "discount_price",
            "final_price",
            "stock",
            "abv",
            "volume_ml",
            "country_of_origin",
            "vintage_year",
            "ibu",
            "taste_notes",
            "serving_temp",
            "is_active",
            "is_featured",
            "category",
            "brand",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProductWriteInputSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True)
    )
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Product
        fields = (
            "category",
            "brand",
            "name",
            "slug",
            "sku",
            "description",
            "price",
            "discount_price",
            "stock",
            "abv",
            "volume_ml",
            "country_of_origin",
            "vintage_year",
            "ibu",
            "taste_notes",
            "serving_temp",
            "is_active",
            "is_featured",
        )

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        discount_price = attrs.get(
            "discount_price",
            getattr(self.instance, "discount_price", None),
        )
        if (
            price is not None
            and discount_price is not None
            and discount_price >= price
        ):
            raise serializers.ValidationError({
                "discount_price": "Discount price must be strictly lower than regular price.",
            })
        return attrs
