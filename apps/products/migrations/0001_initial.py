# Generated manually to match the initial Product app schema.

import uuid
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Brand",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="brands/")),
                ("country", models.CharField(blank=True, max_length=100)),
                ("description", models.TextField(blank=True)),
            ],
            options={"verbose_name": "Brand", "verbose_name_plural": "Brands", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to="categories/")),
                ("is_active", models.BooleanField(default=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="products.category")),
            ],
            options={"verbose_name": "Category", "verbose_name_plural": "Categories", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=280, unique=True)),
                ("sku", models.CharField(max_length=50, unique=True)),
                ("description", models.TextField()),
                ("price", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("discount_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("stock", models.PositiveIntegerField(default=0)),
                ("abv", models.DecimalField(decimal_places=1, help_text="Alcohol By Volume (%) - درصد الکل مثلاً 5.0 یا 40.0", max_digits=4, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(100.0)])),
                ("volume_ml", models.PositiveIntegerField(help_text="حجم به میلی‌لیتر - مثلاً 330 یا 750")),
                ("country_of_origin", models.CharField(blank=True, help_text="کشور سازنده - مثلاً آلمان، فرانسه", max_length=100)),
                ("vintage_year", models.PositiveIntegerField(blank=True, help_text="سال ساخت (مخصوص شراب یا ویسکی‌های خاص)", null=True)),
                ("ibu", models.PositiveIntegerField(blank=True, help_text="شاخص تلخی International Bitterness Units (مخصوص آبجو)", null=True)),
                ("taste_notes", models.TextField(blank=True, help_text="طعم و نت‌های نوشیدنی (مثلاً میوه‌ای، تلخ، چوبی)")),
                ("serving_temp", models.CharField(blank=True, help_text="دمای پیشنهادی سرو (مثلاً 4-7°C)", max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("is_featured", models.BooleanField(default=False)),
                ("brand", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="products.brand")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="products.category")),
            ],
            options={
                "verbose_name": "Product",
                "verbose_name_plural": "Products",
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("discount_price__isnull", True)) | models.Q(("discount_price__lt", models.F("price"))),
                        name="product_discount_lower_than_price",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image", models.ImageField(upload_to="products/")),
                ("is_primary", models.BooleanField(default=False)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="products.product")),
            ],
            options={
                "verbose_name": "Product Image",
                "verbose_name_plural": "Product Images",
                "ordering": ["display_order", "id"],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_primary", True)), fields=("product",), name="one_primary_image_per_product"),
                ],
            },
        ),
    ]
