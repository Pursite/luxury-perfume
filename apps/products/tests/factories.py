import factory
from factory.django import DjangoModelFactory, ImageField
from apps.products.models import Category, Brand, Product, ProductImage


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    is_active = True


class BrandFactory(DjangoModelFactory):
    class Meta:
        model = Brand

    name = factory.Sequence(lambda n: f"Brand {n}")
    slug = factory.Sequence(lambda n: f"brand-{n}")
    country = "France"
    description = "Premium wine brand"


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    category = factory.SubFactory(CategoryFactory)
    brand = factory.SubFactory(BrandFactory)
    name = factory.Sequence(lambda n: f"Wine Product {n}")
    slug = factory.Sequence(lambda n: f"wine-product-{n}")
    sku = factory.Sequence(lambda n: f"SKU-{n:05d}")
    description = "A fine vintage wine with rich fruit aromas."
    price = 100.00
    discount_price = 80.00
    stock = 50
    abv = 13.5
    volume_ml = 750
    country_of_origin = "France"
    vintage_year = 2020
    taste_notes = "Fruity, oaky, smooth finish"
    is_active = True
    is_featured = False


class ProductImageFactory(DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = ImageField(color="red", width=200, height=200)
    is_primary = False
    display_order = 0