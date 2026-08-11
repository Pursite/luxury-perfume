import factory
from factory.django import DjangoModelFactory, ImageField
from apps.products.models import Brand, Category, FragranceNote, Product, ProductImage


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
    description = "Independent luxury fragrance house"


class FragranceNoteFactory(DjangoModelFactory):
    class Meta:
        model = FragranceNote

    name = factory.Sequence(lambda n: f"Fragrance Note {n}")
    slug = factory.Sequence(lambda n: f"fragrance-note-{n}")


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    category = factory.SubFactory(CategoryFactory)
    brand = factory.SubFactory(BrandFactory)
    name = factory.Sequence(lambda n: f"Fragrance Product {n}")
    slug = factory.Sequence(lambda n: f"fragrance-product-{n}")
    sku = factory.Sequence(lambda n: f"SKU-{n:05d}")
    description = "A refined floral fragrance with a warm musk dry-down."
    price = 100.00
    discount_price = 80.00
    stock = 50
    concentration = Product.Concentration.EAU_DE_PARFUM
    volume_ml = 100
    country_of_origin = "France"
    target_audience = Product.TargetAudience.UNISEX
    fragrance_family = Product.FragranceFamily.FLORAL
    introduction_year = 2020
    suitable_season = Product.SuitableSeason.ALL_SEASONS
    suitable_usage_time = Product.SuitableUsageTime.DAY_AND_NIGHT
    is_active = True
    is_featured = False


class ProductImageFactory(DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = ImageField(color="red", width=200, height=200)
    is_primary = False
    display_order = 0
