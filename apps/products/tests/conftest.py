import shutil
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.products.tests.factories import BrandFactory, CategoryFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def admin_user():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def normal_user():
    return UserFactory(is_staff=False)


@pytest.fixture
def image_file():
    def create_image(name="test-image.jpg"):
        content = BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(content, "JPEG")
        return SimpleUploadedFile(
            name,
            content.getvalue(),
            content_type="image/jpeg",
        )

    return create_image


@pytest.fixture
def product_payload():
    category = CategoryFactory()
    brand = BrandFactory()
    return {
        "category": str(category.id),
        "brand": str(brand.id),
        "name": "Aurora Eau de Parfum",
        "slug": "aurora-eau-de-parfum",
        "sku": "AUR-2026-001",
        "description": "A luminous floral fragrance with a soft musk base.",
        "price": "150.00",
        "discount_price": "120.00",
        "stock": 100,
        "concentration": "eau_de_parfum",
        "volume_ml": 100,
        "country_of_origin": "France",
        "target_audience": "unisex",
        "fragrance_family": "floral",
        "introduction_year": 2024,
        "suitable_season": "all_seasons",
        "suitable_usage_time": "day_and_night",
        "is_active": True,
        "is_featured": True,
    }


@pytest.fixture(autouse=True)
def isolated_product_media_root(tmp_path):
    """Keep Product upload tests out of the repository media directory."""
    media_root = tmp_path / "product-media"
    with override_settings(MEDIA_ROOT=media_root):
        yield
    shutil.rmtree(media_root, ignore_errors=True)
