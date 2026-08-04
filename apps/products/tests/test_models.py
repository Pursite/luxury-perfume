from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import BigAutoField

from apps.products.models import Category, Product, ProductImage
from apps.products.tests.factories import ProductFactory, ProductImageFactory


pytestmark = pytest.mark.django_db


def test_product_uses_integer_internal_key_and_public_uuid():
    product = ProductFactory()

    assert isinstance(Product._meta.pk, BigAutoField)
    assert isinstance(product.id, int)
    assert product.uuid


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


def test_database_rejects_non_lower_discount():
    product = ProductFactory.build(
        price=Decimal("100.00"),
        discount_price=Decimal("100.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        product.save(force_insert=True)

    assert not Product.objects.filter(sku=product.sku).exists()


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

