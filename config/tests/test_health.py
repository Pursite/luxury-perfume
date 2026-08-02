from django.apps import apps
from django.db import DatabaseError
import pytest


pytestmark = pytest.mark.django_db


def test_liveness_is_public_and_reports_process_responsiveness(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_required_dependencies(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "security_cache": "ok",
    }


def test_readiness_returns_503_when_database_is_unavailable(client, mocker):
    mocker.patch(
        "django.db.backends.utils.CursorWrapper.execute",
        side_effect=DatabaseError("database unavailable"),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["database"] == "unavailable"


def test_readiness_returns_503_when_security_cache_is_unavailable(client, mocker):
    mocker.patch(
        "django.core.cache.backends.locmem.LocMemCache.set",
        side_effect=OSError("redis unavailable"),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["security_cache"] == "unavailable"


def test_startup_reports_django_app_registry_initialization(client):
    response = client.get("/health/startup")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_returns_503_before_django_app_registry_is_ready(client, mocker):
    mocker.patch.object(apps, "ready", False)

    response = client.get("/health/startup")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
