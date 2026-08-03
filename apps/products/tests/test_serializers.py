from io import BytesIO
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.products.serializers import (
    BrandImageInputSerializer,
    CategoryImageInputSerializer,
    ProductImageUploadInputSerializer,
    ProductWriteInputSerializer,
)
from apps.products.tests.factories import ProductFactory


def test_category_and_brand_reuse_image_content_validation():
    payload = BytesIO()
    Image.new("RGB", (10, 10)).save(payload, "JPEG")
    upload = SimpleUploadedFile(
        "../../unsafe.jpg",
        payload.getvalue(),
        content_type="image/jpeg",
    )

    assert CategoryImageInputSerializer(data={"image": upload}).is_valid()
    upload.seek(0)
    assert BrandImageInputSerializer(data={"logo": upload}).is_valid()


def test_product_image_rejects_mime_type_mismatching_content(image_file):
    original = image_file("wine.jpg")
    upload = SimpleUploadedFile(
        "wine.png",
        original.read(),
        content_type="image/png",
    )

    serializer = ProductImageUploadInputSerializer(data={"image": upload})

    assert serializer.is_valid() is False
    assert "image" in serializer.errors


@pytest.mark.django_db
def test_product_update_serializer_rejects_discount_equal_to_existing_price():
    product = ProductFactory(
        price=Decimal("100.00"),
        discount_price=Decimal("80.00"),
    )
    serializer = ProductWriteInputSerializer(
        product,
        data={"discount_price": "100.00"},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert str(serializer.errors["discount_price"][0]) == (
        "Discount price must be strictly lower than regular price."
    )
