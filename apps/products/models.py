import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

from apps.lib.basemodel import BaseModel


def validate_introduction_year(value: int) -> None:
    if value > date.today().year:
        raise ValidationError("Introduction year cannot be in the future.")


def validate_public_product_slug(value: str) -> None:
    if value != value.lower():
        raise ValidationError("Slug must use lowercase characters.")

    try:
        parsed_uuid = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        return
    if str(parsed_uuid) == value:
        raise ValidationError("Slug must not use canonical UUID syntax.")


class Category(BaseModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if not self.parent_id:
            return

        current = self.parent
        visited_ids = set()
        while current is not None:
            if current.pk == self.pk or current.pk in visited_ids:
                raise ValidationError({"parent": "A category cannot be its own ancestor."})
            visited_ids.add(current.pk)
            current = current.parent

    def save(self, *args, **kwargs):
        # Category writes have no dedicated service path, so enforce hierarchy
        # integrity for normal model/admin saves as well as form validation.
        self.clean()
        return super().save(*args, **kwargs)


class Brand(BaseModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    logo = models.ImageField(upload_to="brands/", null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FragranceNote(BaseModel):
    """A reusable fragrance note that can appear at any stage of a scent."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name = "Fragrance Note"
        verbose_name_plural = "Fragrance Notes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(BaseModel):
    """A product with an internal integer key, stable UUID, and public slug."""

    class Concentration(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        EXTRAIT_DE_PARFUM = "extrait_de_parfum", "Extrait de Parfum"
        PARFUM = "parfum", "Parfum"
        EAU_DE_PARFUM = "eau_de_parfum", "Eau de Parfum"
        EAU_DE_TOILETTE = "eau_de_toilette", "Eau de Toilette"
        EAU_DE_COLOGNE = "eau_de_cologne", "Eau de Cologne"

    class TargetAudience(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        WOMEN = "women", "Women"
        MEN = "men", "Men"
        UNISEX = "unisex", "Unisex"
        KIDS = "kids", "Kids"

    class FragranceFamily(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        AMBER = "amber", "Amber"
        AROMATIC = "aromatic", "Aromatic"
        AQUATIC = "aquatic", "Aquatic"
        CHYPRE = "chypre", "Chypre"
        CITRUS = "citrus", "Citrus"
        FLORAL = "floral", "Floral"
        FOUGERE = "fougere", "Fougere"
        FRUITY = "fruity", "Fruity"
        GOURMAND = "gourmand", "Gourmand"
        GREEN = "green", "Green"
        LEATHER = "leather", "Leather"
        MUSK = "musk", "Musk"
        POWDERY = "powdery", "Powdery"
        SPICY = "spicy", "Spicy"
        WOODY = "woody", "Woody"
        OTHER = "other", "Other"

    class SuitableSeason(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        SPRING = "spring", "Spring"
        SUMMER = "summer", "Summer"
        AUTUMN = "autumn", "Autumn"
        WINTER = "winter", "Winter"
        ALL_SEASONS = "all_seasons", "All seasons"

    class SuitableUsageTime(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        DAY = "day", "Day"
        NIGHT = "night", "Night"
        DAY_AND_NIGHT = "day_and_night", "Day and night"

    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    sku = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock = models.PositiveIntegerField(default=0)
    concentration = models.CharField(
        max_length=32,
        choices=Concentration.choices,
        default=Concentration.UNSPECIFIED,
    )
    volume_ml = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Package volume in millilitres.",
    )
    country_of_origin = models.CharField(
        max_length=100,
        blank=True,
        help_text="Country where the product was made.",
    )
    target_audience = models.CharField(
        max_length=16,
        choices=TargetAudience.choices,
        default=TargetAudience.UNSPECIFIED,
    )
    fragrance_family = models.CharField(
        max_length=16,
        choices=FragranceFamily.choices,
        default=FragranceFamily.UNSPECIFIED,
        help_text="Primary fragrance family or main accord.",
    )
    introduction_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1700), validate_introduction_year],
        help_text="Year the fragrance was introduced.",
    )
    suitable_season = models.CharField(
        max_length=16,
        choices=SuitableSeason.choices,
        default=SuitableSeason.UNSPECIFIED,
    )
    suitable_usage_time = models.CharField(
        max_length=16,
        choices=SuitableUsageTime.choices,
        default=SuitableUsageTime.UNSPECIFIED,
    )
    fragrance_notes = models.ManyToManyField(
        FragranceNote,
        blank=True,
        related_name="products",
        through="ProductFragranceNote",
    )
    barcode = models.CharField(
        max_length=14,
        null=True,
        blank=True,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[0-9]{8,14}$",
                message="Barcode must contain between 8 and 14 digits.",
            ),
        ],
        help_text="Optional 8-14 digit retail barcode; distinct from the SKU.",
    )
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_price__isnull=True)
                | Q(discount_price__lt=F("price")),
                name="product_discount_lower_than_price",
            ),
            models.CheckConstraint(
                condition=Q(volume_ml__gte=1),
                name="product_positive_volume_ml",
            ),
            models.CheckConstraint(
                condition=Q(introduction_year__isnull=True)
                | Q(introduction_year__gte=1700),
                name="product_introduction_year_not_before_1700",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.volume_ml}ml)"

    def clean(self) -> None:
        super().clean()
        try:
            validate_public_product_slug(self.slug)
        except ValidationError as exc:
            raise ValidationError({"slug": exc.messages}) from exc
        if (
            self.price is not None
            and self.discount_price is not None
            and self.discount_price >= self.price
        ):
            raise ValidationError({
                "discount_price": "Discount price must be strictly lower than regular price.",
            })

    @property
    def final_price(self):
        return self.discount_price if self.discount_price is not None else self.price


class ProductFragranceNote(models.Model):
    """An explicitly ordered fragrance note within one product pyramid layer."""

    class Layer(models.TextChoices):
        TOP = "top", "Top"
        MIDDLE = "middle", "Middle"
        BASE = "base", "Base"

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="fragrance_note_links",
    )
    fragrance_note = models.ForeignKey(
        FragranceNote,
        on_delete=models.CASCADE,
        related_name="product_links",
    )
    layer = models.CharField(max_length=6, choices=Layer.choices)
    position = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="1-based order within this product and layer.",
    )

    class Meta:
        verbose_name = "Product Fragrance Note"
        verbose_name_plural = "Product Fragrance Notes"
        ordering = ["layer", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "layer", "fragrance_note"],
                name="unique_product_note_per_layer",
            ),
            models.UniqueConstraint(
                fields=["product", "layer", "position"],
                name="unique_product_note_position",
            ),
            models.CheckConstraint(
                condition=Q(position__gte=1),
                name="product_note_position_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(layer__in=("top", "middle", "base")),
                name="product_note_valid_layer",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.product.name}: {self.get_layer_display()} "
            f"#{self.position} {self.fragrance_note.name}"
        )


class ProductImage(BaseModel):
    """An image uses an internal integer identifier; product URLs never do."""

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/")
    thumbnail = models.ImageField(upload_to="products/thumbnails/", blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="one_primary_image_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"Image for {self.product.name}"
