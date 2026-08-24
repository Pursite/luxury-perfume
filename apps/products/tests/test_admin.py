from io import BytesIO

import pytest
from django.contrib import admin
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import RequestFactory
from PIL import Image

from apps.products.admin import ProductImageInline
from apps.products.models import Product, ProductImage
from apps.products.services import create_product_image_in_transaction_service
from apps.products.tests.factories import ProductFactory, ProductImageFactory
from apps.users.tests.factories import UserFactory


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


def _admin_request():
    request = RequestFactory().post("/admin/products/product/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    request._created_product_images = []
    return request


def _product_image_formset(*, request, product, data, files=None):
    inline = ProductImageInline(Product, admin.site)
    formset_class = inline.get_formset(request, product)
    return formset_class(
        data=data,
        files=files,
        instance=product,
        prefix="images",
    )


def _management_data(*, total_forms, initial_forms):
    return {
        "images-TOTAL_FORMS": str(total_forms),
        "images-INITIAL_FORMS": str(initial_forms),
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
    }


def test_product_image_inline_create_uses_validated_service_lifecycle(
    image_file,
    django_capture_on_commit_callbacks,
    mocker,
):
    product = ProductFactory()
    existing_primary = ProductImageFactory(product=product, is_primary=True)
    request = _admin_request()
    formset = _product_image_formset(
        request=request,
        product=product,
        data={
            **_management_data(total_forms=1, initial_forms=0),
            "images-0-is_primary": "on",
            "images-0-display_order": "3",
        },
        files={"images-0-image": image_file("admin-upload.jpg")},
    )
    thumbnail_delay = mocker.patch(
        "apps.products.services.generate_product_image_thumbnail.delay"
    )

    assert formset.is_valid(), formset.errors
    with django_capture_on_commit_callbacks(execute=True):
        admin.site._registry[Product].save_formset(
            request,
            form=None,
            formset=formset,
            change=True,
        )

    created_image = ProductImage.objects.exclude(pk=existing_primary.pk).get()
    existing_primary.refresh_from_db()
    assert created_image.image.name.startswith("products/")
    assert created_image.image.name != "products/admin-upload.jpg"
    assert created_image.is_primary is True
    assert created_image.display_order == 3
    assert existing_primary.is_primary is False
    thumbnail_delay.assert_called_once_with(created_image.pk)


def test_product_image_inline_rejects_mime_mismatching_upload(image_file):
    product = ProductFactory()
    request = _admin_request()
    jpeg_upload = image_file("admin-image.jpg")
    mismatched_upload = SimpleUploadedFile(
        "admin-image.png",
        jpeg_upload.read(),
        content_type="image/png",
    )
    formset = _product_image_formset(
        request=request,
        product=product,
        data={
            **_management_data(total_forms=1, initial_forms=0),
            "images-0-display_order": "0",
        },
        files={"images-0-image": mismatched_upload},
    )

    assert formset.is_valid() is False
    assert "Image content does not match its MIME type." in str(
        formset.forms[0].errors["image"]
    )


def test_product_image_inline_delete_cleans_original_and_thumbnail_after_commit(
    django_capture_on_commit_callbacks,
):
    product_image = ProductImageFactory()
    thumbnail_content = BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(thumbnail_content, "WEBP")
    product_image.thumbnail.save(
        "admin-delete-thumbnail.webp",
        ContentFile(thumbnail_content.getvalue()),
        save=True,
    )
    storage = product_image.image.storage
    image_names = [product_image.image.name, product_image.thumbnail.name]
    request = _admin_request()
    formset = _product_image_formset(
        request=request,
        product=product_image.product,
        data={
            **_management_data(total_forms=1, initial_forms=1),
            "images-0-id": str(product_image.pk),
            "images-0-is_primary": "" if not product_image.is_primary else "on",
            "images-0-display_order": str(product_image.display_order),
            "images-0-DELETE": "on",
        },
    )

    assert formset.is_valid(), formset.errors
    with django_capture_on_commit_callbacks(execute=True):
        admin.site._registry[Product].save_formset(
            request,
            form=None,
            formset=formset,
            change=True,
        )

    assert ProductImage.objects.filter(pk=product_image.pk).exists() is False
    assert all(storage.exists(image_name) is False for image_name in image_names)


def test_product_admin_cleans_new_original_after_outer_transaction_rollback(
    image_file,
    mocker,
):
    product = ProductFactory()
    request = _admin_request()
    product_admin = admin.site._registry[Product]
    storage = ProductImage._meta.get_field("image").storage
    created_image_name = None

    def fail_after_inline_save(*args, **kwargs):
        nonlocal created_image_name
        with transaction.atomic():
            product_image = create_product_image_in_transaction_service(
                product=product,
                image_file=image_file("admin-rollback.jpg"),
                is_primary=False,
                display_order=0,
            )
            request._created_product_images.append(product_image)
            created_image_name = product_image.image.name
            assert storage.exists(created_image_name)
            raise RuntimeError("later admin save failed")

    mocker.patch.object(
        admin.ModelAdmin,
        "changeform_view",
        side_effect=fail_after_inline_save,
    )

    with pytest.raises(RuntimeError, match="later admin save failed"):
        product_admin.changeform_view(request, object_id=str(product.pk))

    assert created_image_name is not None
    assert ProductImage.objects.filter(image=created_image_name).exists() is False
    assert storage.exists(created_image_name) is False
