import pytest
from django.contrib import admin

from apps.products.models import Product
from apps.products.tests.factories import ProductFactory


pytestmark = pytest.mark.django_db


def test_product_admin_allows_slug_on_create_and_freezes_it_afterward():
    product_admin = admin.site._registry[Product]
    product = ProductFactory()

    assert "slug" not in product_admin.get_readonly_fields(None, obj=None)
    assert product_admin.get_prepopulated_fields(None, obj=None) == {
        "slug": ("name",),
    }
    assert "slug" in product_admin.get_readonly_fields(None, obj=product)
    assert product_admin.get_prepopulated_fields(None, obj=product) == {}
