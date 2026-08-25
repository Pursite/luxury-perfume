from io import BytesIO
import time

import pytest
from django.core.cache import caches
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status

from apps.products.models import Product, ProductFragranceNote, ProductImage
from apps.products.tests.factories import (
    BrandFactory,
    CategoryFactory,
    FragranceNoteFactory,
    ProductFactory,
    ProductImageFactory,
)
from apps.users.tests.factories import UserFactory


def _add_note(product, note, layer, position=1):
    return ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=note,
        layer=layer,
        position=position,
    )


@pytest.mark.django_db
class TestProductListCreateAPIView:
    url = reverse("apps.products:product-list")

    def test_list_is_paginated_and_hides_inactive_products(self, api_client):
        products = ProductFactory.create_batch(15, is_active=True)
        ProductFactory(is_active=False)

        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 15
        assert response.data["total_pages"] == 2
        assert len(response.data["results"]) == 12
        assert response.data["results"][0]["uuid"] in {
            str(product.uuid) for product in products
        }
        result = response.data["results"][0]
        assert "id" not in result
        assert {
            "concentration",
            "target_audience",
            "fragrance_family",
            "introduction_year",
            "suitable_season",
            "suitable_usage_time",
        } <= result.keys()
        assert {
            "abv",
            "ibu",
            "vintage_year",
            "taste_notes",
            "serving_temp",
        }.isdisjoint(result)

    def test_anonymous_catalogue_reads_use_a_dedicated_throttle_scope(
        self,
        api_client,
    ):
        ProductFactory()
        caches["default"].set(
            "throttle_catalogue_198.51.100.10",
            [time.time()] * 119,
            timeout=60,
        )

        first_response = api_client.get(self.url, REMOTE_ADDR="198.51.100.10")
        second_response = api_client.get(self.url, REMOTE_ADDR="198.51.100.10")

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_global_anonymous_exhaustion_does_not_block_catalogue_reads(
        self,
        api_client,
    ):
        ProductFactory()
        caches["default"].set(
            "throttle_anon_198.51.100.11",
            [time.time()] * 100,
            timeout=86400,
        )

        response = api_client.get(self.url, REMOTE_ADDR="198.51.100.11")

        assert response.status_code == status.HTTP_200_OK

    def test_authenticated_product_mutations_keep_user_throttling(
        self,
        api_client,
        admin_user,
    ):
        product = ProductFactory()
        api_client.force_authenticate(user=admin_user)
        caches["default"].set(
            f"throttle_user_{admin_user.pk}",
            [time.time()] * 999,
            timeout=86400,
        )

        first_response = api_client.patch(
            reverse(
                "apps.products:product-detail",
                kwargs={"product_slug": product.slug},
            ),
            {"name": "First update"},
            format="json",
        )
        second_response = api_client.patch(
            reverse(
                "apps.products:product-detail",
                kwargs={"product_slug": product.slug},
            ),
            {"name": "Second update"},
            format="json",
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_list_filters_searches_and_orders(self, api_client):
        category = CategoryFactory()
        brand = BrandFactory()
        matching = ProductFactory(
            category=category,
            brand=brand,
            name="Aurora Eau de Parfum",
            sku="AUR-100",
            price="200.00",
            stock=5,
        )
        ProductFactory(
            name="Nocturne Eau de Toilette",
            sku="NOC-200",
            price="50.00",
            discount_price="40.00",
            stock=0,
        )

        response = api_client.get(
            self.url,
            {
                "category": category.slug,
                "brand": str(brand.id),
                "search": "AUR-100",
                "ordering": "-price",
                "in_stock": "true",
                "min_price": "100",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["uuid"] == str(matching.uuid)

    def test_list_category_slug_includes_products_in_descendant_categories(
        self,
        api_client,
    ):
        men = CategoryFactory(name="Men", slug="men")
        cologne = CategoryFactory(name="Cologne", slug="cologne", parent=men)
        eau_de_cologne = CategoryFactory(
            name="Eau de Cologne",
            slug="eau-de-cologne",
            parent=cologne,
        )
        women = CategoryFactory(name="Women", slug="women")
        exact_product = ProductFactory(category=men)
        child_product = ProductFactory(category=cologne)
        descendant_product = ProductFactory(category=eau_de_cologne)
        unrelated_product = ProductFactory(category=women)

        response = api_client.get(self.url, {"category": "men"})

        assert response.status_code == status.HTTP_200_OK
        assert {item["uuid"] for item in response.data["results"]} == {
            str(exact_product.uuid),
            str(child_product.uuid),
            str(descendant_product.uuid),
        }
        assert str(unrelated_product.uuid) not in {
            item["uuid"] for item in response.data["results"]
        }

    def test_list_category_unknown_slug_returns_an_empty_result(self, api_client):
        ProductFactory()

        response = api_client.get(self.url, {"category": "not-a-category"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_list_category_slug_combines_with_in_stock_filter(self, api_client):
        men = CategoryFactory(name="Men", slug="men")
        cologne = CategoryFactory(name="Cologne", slug="cologne", parent=men)
        in_stock = ProductFactory(category=cologne, stock=1)
        ProductFactory(category=men, stock=0)
        ProductFactory(stock=10)

        response = api_client.get(
            self.url,
            {"category": "men", "in_stock": "true"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["uuid"] == str(in_stock.uuid)

    @pytest.mark.parametrize(
        ("query_parameter", "value", "nonmatching_override"),
        [
            ("concentration", "eau_de_parfum", {"concentration": "eau_de_toilette"}),
            ("target_audience", "unisex", {"target_audience": "men"}),
            ("fragrance_family", "floral", {"fragrance_family": "woody"}),
            ("introduction_year", "2020", {"introduction_year": 2024}),
            ("suitable_season", "all_seasons", {"suitable_season": "winter"}),
            (
                "suitable_usage_time",
                "day_and_night",
                {"suitable_usage_time": "night"},
            ),
        ],
    )
    def test_list_filters_by_fragrance_metadata(
        self,
        api_client,
        query_parameter,
        value,
        nonmatching_override,
    ):
        matching = ProductFactory()
        ProductFactory(**nonmatching_override)

        response = api_client.get(self.url, {query_parameter: value})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["uuid"] == str(matching.uuid)

    def test_list_filters_and_searches_by_reusable_fragrance_note(self, api_client):
        bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
        cedar = FragranceNoteFactory(name="Cedar", slug="cedar")
        matching = ProductFactory(name="Aurora")
        other = ProductFactory(name="Nocturne")
        _add_note(matching, bergamot, ProductFragranceNote.Layer.TOP)
        _add_note(matching, bergamot, ProductFragranceNote.Layer.MIDDLE)
        _add_note(other, cedar, ProductFragranceNote.Layer.BASE)

        filtered = api_client.get(self.url, {"note": str(bergamot.id)})
        searched = api_client.get(self.url, {"search": "Bergamot"})

        assert filtered.status_code == status.HTTP_200_OK
        assert filtered.data["count"] == 1
        assert filtered.data["results"][0]["uuid"] == str(matching.uuid)
        assert searched.status_code == status.HTTP_200_OK
        assert searched.data["count"] == 1
        assert searched.data["results"][0]["uuid"] == str(matching.uuid)

    def test_list_orders_by_introduction_year(self, api_client):
        newer = ProductFactory(introduction_year=2024)
        older = ProductFactory(introduction_year=2018)

        response = api_client.get(self.url, {"ordering": "-introduction_year"})

        assert response.status_code == status.HTTP_200_OK
        assert [item["uuid"] for item in response.data["results"]] == [
            str(newer.uuid),
            str(older.uuid),
        ]

    def test_create_requires_admin_and_returns_uuid(
        self,
        api_client,
        admin_user,
        product_payload,
    ):
        bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
        lemon = FragranceNoteFactory(name="Lemon", slug="lemon")
        payload = {
            **product_payload,
            "top_notes": [str(lemon.id), str(bergamot.id)],
        }
        response = api_client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        api_client.force_authenticate(user=admin_user)
        response = api_client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Product.objects.filter(uuid=response.data["uuid"]).exists()
        assert [item["uuid"] for item in response.data["top_notes"]] == [
            str(lemon.id),
            str(bergamot.id),
        ]
        assert "id" not in response.data

    def test_create_rejects_invalid_discount_and_duplicate_sku(
        self,
        api_client,
        admin_user,
        product_payload,
    ):
        api_client.force_authenticate(user=admin_user)
        invalid = {**product_payload, "discount_price": "150.00"}
        response = api_client.post(self.url, invalid, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "discount_price" in response.data

        existing = ProductFactory()
        duplicate = {
            **product_payload,
            "slug": "new-unique-slug",
            "sku": existing.sku,
        }
        response = api_client.post(self.url, duplicate, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "sku" in response.data


@pytest.mark.django_db
class TestProductDetailAPIView:
    def test_detail_uses_canonical_slug_and_hides_inactive_products(self, api_client):
        active = ProductFactory()
        bergamot = FragranceNoteFactory(name="Bergamot", slug="bergamot")
        lemon = FragranceNoteFactory(name="Lemon", slug="lemon")
        jasmine = FragranceNoteFactory(name="Jasmine", slug="jasmine")
        musk = FragranceNoteFactory(name="Musk", slug="musk")
        _add_note(active, lemon, ProductFragranceNote.Layer.TOP, position=1)
        _add_note(active, bergamot, ProductFragranceNote.Layer.TOP, position=2)
        _add_note(active, jasmine, ProductFragranceNote.Layer.MIDDLE)
        _add_note(active, musk, ProductFragranceNote.Layer.BASE)
        inactive = ProductFactory(is_active=False)
        active_url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": active.slug},
        )
        inactive_url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": inactive.slug},
        )

        response = api_client.get(active_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["uuid"] == str(active.uuid)
        assert "id" not in response.data
        assert response.data["top_notes"] == [
            {"uuid": str(lemon.id), "name": "Lemon", "slug": "lemon"},
            {"uuid": str(bergamot.id), "name": "Bergamot", "slug": "bergamot"},
        ]
        assert response.data["middle_notes"][0]["name"] == "Jasmine"
        assert response.data["base_notes"][0]["name"] == "Musk"
        assert {
            "abv",
            "ibu",
            "vintage_year",
            "taste_notes",
            "serving_temp",
        }.isdisjoint(response.data)
        assert api_client.get(inactive_url).status_code == status.HTTP_404_NOT_FOUND
        assert (
            api_client.get(f"/api/v1/products/{active.slug.upper()}/").status_code
            == status.HTTP_404_NOT_FOUND
        )
        assert (
            api_client.get(f"/api/v1/products/{active.uuid}/").status_code
            == status.HTTP_404_NOT_FOUND
        )
        assert api_client.get("/api/v1/products/1/").status_code == status.HTTP_404_NOT_FOUND

    def test_anonymous_detail_reads_use_the_catalogue_throttle(
        self,
        api_client,
    ):
        product = ProductFactory()
        caches["default"].set(
            "throttle_catalogue_198.51.100.12",
            [time.time()] * 119,
            timeout=60,
        )
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": product.slug},
        )

        first_response = api_client.get(url, REMOTE_ADDR="198.51.100.12")
        second_response = api_client.get(url, REMOTE_ADDR="198.51.100.12")

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_put_patch_and_delete_require_admin(self, api_client, admin_user, normal_user):
        product = ProductFactory(name="Original")
        jasmine = FragranceNoteFactory(name="Jasmine", slug="jasmine")
        rose = FragranceNoteFactory(name="Rose", slug="rose")
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": product.slug},
        )

        api_client.force_authenticate(user=normal_user)
        response = api_client.patch(url, {"name": "Blocked"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        api_client.force_authenticate(user=admin_user)
        response = api_client.patch(url, {"name": "Patched"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Patched"

        full_payload = {
            "category": str(product.category.id),
            "brand": str(product.brand.id),
            "name": "Replaced",
            "slug": product.slug,
            "sku": product.sku,
            "description": product.description,
            "price": "100.00",
            "discount_price": "80.00",
            "stock": 10,
            "concentration": "eau_de_parfum",
            "volume_ml": 100,
            "country_of_origin": "France",
            "target_audience": "unisex",
            "fragrance_family": "floral",
            "introduction_year": 2024,
            "suitable_season": "all_seasons",
            "suitable_usage_time": "day_and_night",
            "middle_notes": [str(rose.id), str(jasmine.id)],
            "is_active": True,
            "is_featured": False,
        }
        response = api_client.put(url, full_payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Replaced"
        assert [item["uuid"] for item in response.data["middle_notes"]] == [
            str(rose.id),
            str(jasmine.id),
        ]

        response = api_client.patch(
            url,
            {"middle_notes": [str(jasmine.id), str(rose.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert [item["uuid"] for item in response.data["middle_notes"]] == [
            str(jasmine.id),
            str(rose.id),
        ]

        response = api_client.patch(url, {"middle_notes": []}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["middle_notes"] == []

        response = api_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Product.objects.filter(uuid=product.uuid).exists()

    def test_patch_rejects_slug_change_without_partial_write(
        self,
        api_client,
        admin_user,
    ):
        product = ProductFactory(name="Original", slug="original-slug")
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": product.slug},
        )
        api_client.force_authenticate(user=admin_user)

        response = api_client.patch(
            url,
            {"name": "Must not persist", "slug": "replacement-slug"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(response.data["slug"][0]) == (
            "Slug cannot be changed after product creation."
        )
        product.refresh_from_db()
        assert product.name == "Original"
        assert product.slug == "original-slug"

    def test_unknown_slug_returns_not_found(self, api_client):
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": "missing-product"},
        )

        assert api_client.get(url).status_code == status.HTTP_404_NOT_FOUND

    def test_delete_returns_not_found_when_product_vanishes_before_lock(
        self,
        api_client,
        admin_user,
        mocker,
    ):
        product = ProductFactory()
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_slug": product.slug},
        )
        api_client.force_authenticate(user=admin_user)
        mocker.patch(
            "apps.products.views.delete_product_service",
            return_value=False,
        )

        response = api_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestProductImageAPIView:
    def test_upload_toggles_primary_image_and_uses_product_slug(
        self,
        api_client,
        admin_user,
        image_file,
    ):
        product = ProductFactory()
        existing_primary = ProductImageFactory(product=product, is_primary=True)
        api_client.force_authenticate(user=admin_user)
        url = reverse(
            "apps.products:product-image-upload",
            kwargs={"product_slug": product.slug},
        )

        response = api_client.post(
            url,
            {"image": image_file(), "is_primary": True, "display_order": 1},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert isinstance(response.data["id"], int)
        image = ProductImage.objects.get(id=response.data["id"])
        assert image.product_id == product.id
        assert image.is_primary is True
        existing_primary.refresh_from_db()
        assert existing_primary.is_primary is False

    def test_upload_requires_admin_and_returns_not_found_for_unknown_product(
        self,
        api_client,
        normal_user,
        image_file,
    ):
        product = ProductFactory()
        url = reverse(
            "apps.products:product-image-upload",
            kwargs={"product_slug": product.slug},
        )
        api_client.force_authenticate(user=normal_user)
        assert (
            api_client.post(url, {"image": image_file()}, format="multipart").status_code
            == status.HTTP_403_FORBIDDEN
        )

        api_client.force_authenticate(user=UserFactory(is_staff=True))
        unknown_url = url.replace(
            product.slug,
            "missing-product",
        )
        assert (
            api_client.post(
                unknown_url,
                {"image": image_file()},
                format="multipart",
            ).status_code
            == status.HTTP_404_NOT_FOUND
        )

    def test_delete_image_by_integer_identifier_requires_admin(
        self,
        api_client,
        admin_user,
        normal_user,
    ):
        image = ProductImageFactory()
        url = reverse(
            "apps.products:product-image-delete",
            kwargs={"image_id": image.id},
        )

        api_client.force_authenticate(user=normal_user)
        assert api_client.delete(url).status_code == status.HTTP_403_FORBIDDEN

        api_client.force_authenticate(user=admin_user)
        assert api_client.delete(url).status_code == status.HTTP_204_NO_CONTENT
        assert not ProductImage.objects.filter(id=image.id).exists()
        assert api_client.delete(url).status_code == status.HTTP_404_NOT_FOUND

    def test_delete_returns_not_found_when_image_vanishes_before_lock(
        self,
        api_client,
        admin_user,
        mocker,
    ):
        image = ProductImageFactory()
        url = reverse(
            "apps.products:product-image-delete",
            kwargs={"image_id": image.id},
        )
        api_client.force_authenticate(user=admin_user)
        mocker.patch(
            "apps.products.views.delete_product_image_service",
            return_value=False,
        )

        response = api_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestProductImageUploadValidation:
    def _upload_url(self, product):
        return reverse(
            "apps.products:product-image-upload",
            kwargs={"product_slug": product.slug},
        )

    def test_rejects_disallowed_declared_mime_type(
        self,
        api_client,
        admin_user,
        image_file,
    ):
        product = ProductFactory()
        api_client.force_authenticate(user=admin_user)
        content = BytesIO()
        Image.new("RGB", (20, 20), color="blue").save(content, "GIF")
        upload = SimpleUploadedFile(
            "fragrance.gif",
            content.getvalue(),
            content_type="image/gif",
        )

        response = api_client.post(
            self._upload_url(product),
            {"image": upload},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "image" in response.data

    def test_rejects_corrupted_and_oversized_uploads(self, api_client, admin_user):
        product = ProductFactory()
        api_client.force_authenticate(user=admin_user)

        corrupted = SimpleUploadedFile(
            "corrupted.jpg",
            b"not an image",
            content_type="image/jpeg",
        )
        corrupt_response = api_client.post(
            self._upload_url(product),
            {"image": corrupted},
            format="multipart",
        )

        valid_content = BytesIO()
        Image.new("RGB", (20, 20), color="green").save(valid_content, "JPEG")
        oversized = SimpleUploadedFile(
            "oversized.jpg",
            valid_content.getvalue() + (b"x" * (5 * 1024 * 1024)),
            content_type="image/jpeg",
        )
        oversized_response = api_client.post(
            self._upload_url(product),
            {"image": oversized},
            format="multipart",
        )

        assert corrupt_response.status_code == status.HTTP_400_BAD_REQUEST
        assert oversized_response.status_code == status.HTTP_400_BAD_REQUEST
        assert "image" in corrupt_response.data
        assert "image" in oversized_response.data

    def test_rejects_images_with_excessive_dimensions(self, api_client, admin_user):
        product = ProductFactory()
        api_client.force_authenticate(user=admin_user)
        content = BytesIO()
        Image.new("RGB", (6001, 1), color="green").save(content, "PNG")
        oversized_dimensions = SimpleUploadedFile(
            "too-wide.png",
            content.getvalue(),
            content_type="image/png",
        )

        response = api_client.post(
            self._upload_url(product),
            {"image": oversized_dimensions},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "image" in response.data

    @pytest.mark.django_db(transaction=True)
    def test_upload_sanitizes_filename_and_schedules_thumbnail(
        self,
        api_client,
        admin_user,
        image_file,
        mocker,
    ):
        product = ProductFactory()
        api_client.force_authenticate(user=admin_user)
        task_delay = mocker.patch(
            "apps.products.services.generate_product_image_thumbnail.delay"
        )

        response = api_client.post(
            self._upload_url(product),
            {"image": image_file("../../Perfume bottle.JPG")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        image = ProductImage.objects.get(id=response.data["id"])
        assert ".." not in image.image.name
        assert image.image.name.endswith(".jpg")
        task_delay.assert_called_once_with(image.id)
