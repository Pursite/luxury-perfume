import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from io import BytesIO

from apps.products.models import Brand, Category
from apps.products.serializers import BrandImageInputSerializer, CategoryImageInputSerializer


@pytest.mark.django_db
def test_category_rejects_self_and_indirect_cycles():
    root = Category.objects.create(name="Root", slug="root")
    child = Category.objects.create(name="Child", slug="child", parent=root)
    leaf = Category.objects.create(name="Leaf", slug="leaf", parent=child)
    root.parent = root
    with pytest.raises(ValidationError): root.save()
    root.parent = leaf
    with pytest.raises(ValidationError): root.save()


def test_category_and_brand_reuse_image_content_validation():
    payload = BytesIO(); Image.new("RGB", (10, 10)).save(payload, "JPEG")
    upload = SimpleUploadedFile("../../unsafe.jpg", payload.getvalue(), content_type="image/jpeg")
    assert CategoryImageInputSerializer(data={"image": upload}).is_valid()
    upload.seek(0)
    assert BrandImageInputSerializer(data={"logo": upload}).is_valid()
