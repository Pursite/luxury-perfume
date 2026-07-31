import shutil

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def isolated_product_media_root(tmp_path):
    """Keep Product upload tests out of the repository media directory."""
    media_root = tmp_path / "product-media"
    with override_settings(MEDIA_ROOT=media_root):
        yield
    shutil.rmtree(media_root, ignore_errors=True)
