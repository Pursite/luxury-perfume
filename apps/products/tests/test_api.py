from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status

from apps.products.models import Product, ProductImage
from apps.products.tests.factories import BrandFactory, CategoryFactory, ProductFactory, ProductImageFactory
from apps.users.tests.factories import UserFactory


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
        assert "id" not in response.data["results"][0]

    def test_list_filters_searches_and_orders(self, api_client):
        category = CategoryFactory()
        brand = BrandFactory()
        matching = ProductFactory(
            category=category,
            brand=brand,
            name="Cabernet Sauvignon",
            sku="CAB-100",
            price="200.00",
            stock=5,
        )
        ProductFactory(
            name="Merlot",
            sku="MER-200",
            price="50.00",
            discount_price="40.00",
            stock=0,
        )

        response = api_client.get(
            self.url,
            {
                "category": str(category.id),
                "brand": str(brand.id),
                "search": "CAB-100",
                "ordering": "-price",
                "in_stock": "true",
                "min_price": "100",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["uuid"] == str(matching.uuid)

    def test_create_requires_admin_and_returns_uuid(
        self,
        api_client,
        admin_user,
        product_payload,
    ):
        response = api_client.post(self.url, product_payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        api_client.force_authenticate(user=admin_user)
        response = api_client.post(self.url, product_payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Product.objects.filter(uuid=response.data["uuid"]).exists()
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
    def test_detail_uses_uuid_and_hides_inactive_products(self, api_client):
        active = ProductFactory()
        inactive = ProductFactory(is_active=False)
        active_url = reverse(
            "apps.products:product-detail",
            kwargs={"product_uuid": active.uuid},
        )
        inactive_url = reverse(
            "apps.products:product-detail",
            kwargs={"product_uuid": inactive.uuid},
        )

        response = api_client.get(active_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["uuid"] == str(active.uuid)
        assert "id" not in response.data
        assert api_client.get(inactive_url).status_code == status.HTTP_404_NOT_FOUND
        assert api_client.get("/api/v1/products/1/").status_code == status.HTTP_404_NOT_FOUND

    def test_put_patch_and_delete_require_admin(self, api_client, admin_user, normal_user):
        product = ProductFactory(name="Original")
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_uuid": product.uuid},
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
            "abv": "13.0",
            "volume_ml": 750,
            "country_of_origin": "France",
            "is_active": True,
            "is_featured": False,
        }
        response = api_client.put(url, full_payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Replaced"

        response = api_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Product.objects.filter(uuid=product.uuid).exists()

    def test_unknown_uuid_returns_not_found(self, api_client):
        product = ProductFactory()
        url = reverse(
            "apps.products:product-detail",
            kwargs={"product_uuid": product.uuid},
        ).replace(str(product.uuid), "00000000-0000-0000-0000-000000000000")
        assert api_client.get(url).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestProductImageAPIView:
    def test_upload_toggles_primary_image_and_uses_product_uuid(
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
            kwargs={"product_uuid": product.uuid},
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
            kwargs={"product_uuid": product.uuid},
        )
        api_client.force_authenticate(user=normal_user)
        assert (
            api_client.post(url, {"image": image_file()}, format="multipart").status_code
            == status.HTTP_403_FORBIDDEN
        )

        api_client.force_authenticate(user=UserFactory(is_staff=True))
        unknown_url = url.replace(
            str(product.uuid),
            "00000000-0000-0000-0000-000000000000",
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


@pytest.mark.django_db
class TestProductImageUploadValidation:
    def _upload_url(self, product):
        return reverse(
            "apps.products:product-image-upload",
            kwargs={"product_uuid": product.uuid},
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
            "wine.gif",
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
            {"image": image_file("../../Wine bottle.JPG")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        image = ProductImage.objects.get(id=response.data["id"])
        assert ".." not in image.image.name
        assert image.image.name.endswith(".jpg")
        task_delay.assert_called_once_with(image.id)
