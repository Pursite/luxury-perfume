import pytest


@pytest.fixture(autouse=True)
def isolated_integration_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "integration-media"

