import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.lib.basemodel import BaseModel


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


class Product(BaseModel):
    """A product with an internal integer key and a public UUID."""

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
    abv = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Alcohol By Volume (%) - درصد الکل مثلاً 5.0 یا 40.0",
    )
    volume_ml = models.PositiveIntegerField(
        help_text="حجم به میلی‌لیتر - مثلاً 330 یا 750"
    )
    country_of_origin = models.CharField(
        max_length=100,
        blank=True,
        help_text="کشور سازنده - مثلاً آلمان، فرانسه",
    )
    vintage_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="سال ساخت (مخصوص شراب یا ویسکی‌های خاص)",
    )
    ibu = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="شاخص تلخی International Bitterness Units (مخصوص آبجو)",
    )
    taste_notes = models.TextField(
        blank=True,
        help_text="طعم و نت‌های نوشیدنی (مثلاً میوه‌ای، تلخ، چوبی)",
    )
    serving_temp = models.CharField(
        max_length=50,
        blank=True,
        help_text="دمای پیشنهادی سرو (مثلاً 4-7°C)",
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
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.volume_ml}ml)"

    def clean(self) -> None:
        super().clean()
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
