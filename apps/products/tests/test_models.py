from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import BigAutoField

from apps.products.models import (
    Category,
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = pytest.mark.django_db


def test_product_uses_integer_internal_key_and_public_uuid():
    product = ProductFactory()

    assert isinstance(Product._meta.pk, BigAutoField)
    assert isinstance(product.id, int)
    assert product.uuid


def test_product_schema_uses_fragrance_fields_instead_of_alcohol_fields():
    field_names = {field.name for field in Product._meta.get_fields()}

    assert {
        "concentration",
        "target_audience",
        "fragrance_family",
        "introduction_year",
        "suitable_season",
        "suitable_usage_time",
        "fragrance_notes",
        "barcode",
    } <= field_names
    assert {
        "abv",
        "ibu",
        "vintage_year",
        "taste_notes",
        "serving_temp",
        "top_notes",
        "middle_notes",
        "base_notes",
    }.isdisjoint(field_names)


def test_category_rejects_self_and_indirect_cycles():
    root = Category.objects.create(name="Root", slug="root")
    child = Category.objects.create(name="Child", slug="child", parent=root)
    leaf = Category.objects.create(name="Leaf", slug="leaf", parent=child)

    root.parent = root
    with pytest.raises(ValidationError) as self_error:
        root.save()
    assert self_error.value.message_dict == {
        "parent": ["A category cannot be its own ancestor."]
    }

    root.parent = leaf
    with pytest.raises(ValidationError) as indirect_error:
        root.save()
    assert indirect_error.value.message_dict == {
        "parent": ["A category cannot be its own ancestor."]
    }


def test_product_model_validation_rejects_non_lower_discount():
    product = ProductFactory.build(
        price=Decimal("100.00"),
        discount_price=Decimal("100.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        product.full_clean()

    assert exc_info.value.message_dict["discount_price"] == [
        "Discount price must be strictly lower than regular price."
    ]


@pytest.mark.parametrize(
    ("slug", "message"),
    [
        ("Aurora-Parfum", "Slug must use lowercase characters."),
        (
            "550e8400-e29b-41d4-a716-446655440000",
            "Slug must not use canonical UUID syntax.",
        ),
    ],
)
def test_product_model_rejects_noncanonical_public_slug(slug, message):
    product = ProductFactory.build(slug=slug)

    with pytest.raises(ValidationError) as exc_info:
        product.full_clean()

    assert exc_info.value.message_dict["slug"] == [message]


@pytest.mark.parametrize(
    ("overrides", "invalid_field"),
    [
        ({"volume_ml": 0}, "volume_ml"),
        ({"introduction_year": 1699}, "introduction_year"),
        ({"introduction_year": date.today().year + 1}, "introduction_year"),
        ({"barcode": "ABC-12345"}, "barcode"),
        ({"barcode": "۱۲۳۴۵۶۷۸"}, "barcode"),
        ({"concentration": "invalid-concentration"}, "concentration"),
    ],
)
def test_product_model_rejects_invalid_fragrance_metadata(overrides, invalid_field):
    product = ProductFactory.build(**overrides)

    with pytest.raises(ValidationError) as exc_info:
        product.full_clean()

    assert invalid_field in exc_info.value.message_dict


def test_body_splash_is_a_category_not_a_concentration():
    category = Category.objects.create(name="Body Splash", slug="body-splash")
    product = ProductFactory.build(
        category=category,
        brand=None,
        concentration=Product.Concentration.UNSPECIFIED,
    )

    product.full_clean()

    assert "body_splash" not in Product.Concentration.values
    assert product.category == category


def test_database_rejects_non_lower_discount():
    product = ProductFactory.build(
        price=Decimal("100.00"),
        discount_price=Decimal("100.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        product.save(force_insert=True)

    assert not Product.objects.filter(sku=product.sku).exists()


@pytest.mark.parametrize(
    ("overrides", "constraint_name"),
    [
        ({"volume_ml": 0}, "product_positive_volume_ml"),
        ({"introduction_year": 1699}, "product_introduction_year_not_before_1700"),
    ],
)
def test_database_rejects_invalid_bounded_fragrance_metadata(
    overrides,
    constraint_name,
):
    product = ProductFactory.build(**overrides)

    with pytest.raises(IntegrityError) as exc_info, transaction.atomic():
        product.save(force_insert=True)

    assert constraint_name in str(exc_info.value)


def test_database_rejects_duplicate_nonempty_barcode():
    ProductFactory(barcode="12345678")
    duplicate = ProductFactory.build(barcode="12345678")

    with pytest.raises(IntegrityError), transaction.atomic():
        duplicate.save(force_insert=True)


def test_fragrance_note_can_be_reused_across_product_layers():
    product = ProductFactory()
    note = FragranceNote.objects.create(
        name="Bergamot",
        slug="bergamot",
    )

    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=note,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=note,
        layer=ProductFragranceNote.Layer.MIDDLE,
        position=1,
    )

    assert list(product.fragrance_notes.distinct()) == [note]
    assert product.fragrance_note_links.count() == 2


@pytest.mark.parametrize(
    "duplicate",
    [
        {"position": 2},
        {"fragrance_note": "second"},
    ],
)
def test_database_prevents_duplicate_note_or_position_within_layer(duplicate):
    product = ProductFactory()
    first_note = FragranceNote.objects.create(name="Bergamot", slug="bergamot")
    second_note = FragranceNote.objects.create(name="Lemon", slug="lemon")
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=first_note,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )
    values = {
        "product": product,
        "fragrance_note": first_note,
        "layer": ProductFragranceNote.Layer.TOP,
        "position": 1,
    }
    values.update(duplicate)
    if values["fragrance_note"] == "second":
        values["fragrance_note"] = second_note

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFragranceNote.objects.create(**values)


def test_database_rejects_nonpositive_fragrance_note_position():
    product = ProductFactory()
    note = FragranceNote.objects.create(name="Bergamot", slug="bergamot")

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFragranceNote.objects.create(
            product=product,
            fragrance_note=note,
            layer=ProductFragranceNote.Layer.BASE,
            position=0,
        )


def test_database_rejects_unknown_fragrance_note_layer():
    product = ProductFactory()
    note = FragranceNote.objects.create(name="Bergamot", slug="bergamot")

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFragranceNote.objects.create(
            product=product,
            fragrance_note=note,
            layer="opening",
            position=1,
        )


def test_database_allows_only_one_primary_image_per_product():
    product = ProductFactory()
    first = ProductImageFactory(product=product, is_primary=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductImageFactory(product=product, is_primary=True)

    assert list(
        ProductImage.objects.filter(product=product, is_primary=True).values_list(
            "pk",
            flat=True,
        )
    ) == [first.pk]
