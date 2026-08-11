from datetime import date
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
from apps.products.tests.factories import FragranceNoteFactory, ProductFactory


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
    original = image_file("fragrance.jpg")
    upload = SimpleUploadedFile(
        "fragrance.png",
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


@pytest.mark.django_db
def test_product_write_serializer_accepts_reusable_fragrance_notes(product_payload):
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    jasmine = FragranceNoteFactory(name="Jasmine", slug="jasmine")
    musk = FragranceNoteFactory(name="Musk", slug="musk")
    payload = {
        **product_payload,
        "barcode": "1234567890123",
        "top_notes": [str(bergamot.id)],
        "middle_notes": [str(jasmine.id)],
        "base_notes": [str(musk.id)],
    }

    serializer = ProductWriteInputSerializer(data=payload)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["top_notes"] == [bergamot]
    assert serializer.validated_data["middle_notes"] == [jasmine]
    assert serializer.validated_data["base_notes"] == [musk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("introduction_year", date.today().year + 1),
        ("barcode", "contains-letters"),
        ("concentration", "invalid-concentration"),
        ("concentration", "body_splash"),
        ("target_audience", "invalid-audience"),
        ("fragrance_family", "invalid-family"),
        ("top_notes", ["00000000-0000-0000-0000-000000000000"]),
    ],
)
def test_product_write_serializer_rejects_invalid_fragrance_metadata(
    product_payload,
    field,
    value,
):
    serializer = ProductWriteInputSerializer(
        data={**product_payload, field: value},
    )

    assert serializer.is_valid() is False
    assert field in serializer.errors


@pytest.mark.django_db
def test_product_write_serializer_rejects_duplicate_notes_within_a_layer(
    product_payload,
):
    bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    serializer = ProductWriteInputSerializer(
        data={
            **product_payload,
            "top_notes": [str(bergamot.id), str(bergamot.id)],
        },
    )

    assert serializer.is_valid() is False
    assert "top_notes" in serializer.errors


@pytest.mark.django_db
def test_product_write_serializer_normalizes_blank_barcode(product_payload):
    serializer = ProductWriteInputSerializer(
        data={**product_payload, "barcode": ""},
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["barcode"] is None


@pytest.mark.django_db
def test_product_write_serializer_rejects_duplicate_barcode(product_payload):
    ProductFactory(barcode="1234567890123")
    serializer = ProductWriteInputSerializer(
        data={**product_payload, "barcode": "1234567890123"},
    )

    assert serializer.is_valid() is False
    assert "barcode" in serializer.errors
