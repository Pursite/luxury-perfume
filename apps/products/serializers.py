from rest_framework import serializers

from apps.lib.image_validation import (
    RestrictedImageField,
    ValidatedCatalogueImageSerializer,
)
from apps.products.models import (
    Brand,
    Category,
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)


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


class FragranceNoteSummarySerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = FragranceNote
        fields = ("uuid", "name", "slug")


class ProductImageOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "thumbnail", "is_primary", "display_order")
        read_only_fields = fields


class ProductImageUploadInputSerializer(ValidatedCatalogueImageSerializer):
    image = RestrictedImageField()
    is_primary = serializers.BooleanField(default=False)
    display_order = serializers.IntegerField(min_value=0, default=0)

    def validate_image(self, value):
        return self.validate_catalogue_image(value)


class CategoryImageInputSerializer(ValidatedCatalogueImageSerializer):
    image = RestrictedImageField()

    def validate_image(self, value):
        return self.validate_catalogue_image(value)


class BrandImageInputSerializer(ValidatedCatalogueImageSerializer):
    logo = RestrictedImageField()
    image_field_name = "brand-logo"

    def validate_logo(self, value):
        return self.validate_catalogue_image(value)


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
            "concentration",
            "target_audience",
            "fragrance_family",
            "introduction_year",
            "suitable_season",
            "suitable_usage_time",
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
    top_notes = serializers.SerializerMethodField()
    middle_notes = serializers.SerializerMethodField()
    base_notes = serializers.SerializerMethodField()
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
            "concentration",
            "target_audience",
            "fragrance_family",
            "introduction_year",
            "suitable_season",
            "suitable_usage_time",
            "volume_ml",
            "country_of_origin",
            "barcode",
            "top_notes",
            "middle_notes",
            "base_notes",
            "is_active",
            "is_featured",
            "category",
            "brand",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _get_ordered_note_links(self, product: Product):
        prefetched = getattr(product, "_ordered_fragrance_note_links", None)
        if prefetched is not None:
            return prefetched

        cached = getattr(product, "_serialized_fragrance_note_links", None)
        if cached is None:
            cached = list(
                product.fragrance_note_links.select_related("fragrance_note").order_by(
                    "layer",
                    "position",
                    "id",
                )
            )
            product._serialized_fragrance_note_links = cached
        return cached

    def _serialize_note_layer(self, product: Product, layer: str):
        notes = [
            link.fragrance_note
            for link in self._get_ordered_note_links(product)
            if link.layer == layer
        ]
        return FragranceNoteSummarySerializer(
            notes,
            many=True,
            context=self.context,
        ).data

    def get_top_notes(self, product: Product):
        return self._serialize_note_layer(product, ProductFragranceNote.Layer.TOP)

    def get_middle_notes(self, product: Product):
        return self._serialize_note_layer(product, ProductFragranceNote.Layer.MIDDLE)

    def get_base_notes(self, product: Product):
        return self._serialize_note_layer(product, ProductFragranceNote.Layer.BASE)


class ProductWriteInputSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True)
    )
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        allow_null=True,
        required=False,
    )
    top_notes = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=FragranceNote.objects.all(),
        required=False,
    )
    middle_notes = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=FragranceNote.objects.all(),
        required=False,
    )
    base_notes = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=FragranceNote.objects.all(),
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
            "concentration",
            "target_audience",
            "fragrance_family",
            "introduction_year",
            "suitable_season",
            "suitable_usage_time",
            "volume_ml",
            "country_of_origin",
            "barcode",
            "top_notes",
            "middle_notes",
            "base_notes",
            "is_active",
            "is_featured",
        )

    def validate_barcode(self, value):
        return value or None

    def _validate_note_layer(self, notes):
        if len(notes) != len({note.pk for note in notes}):
            raise serializers.ValidationError(
                "A fragrance note may appear only once in each layer."
            )
        return notes

    def validate_top_notes(self, notes):
        return self._validate_note_layer(notes)

    def validate_middle_notes(self, notes):
        return self._validate_note_layer(notes)

    def validate_base_notes(self, notes):
        return self._validate_note_layer(notes)

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
