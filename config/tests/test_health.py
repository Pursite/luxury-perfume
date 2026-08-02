import pytest
from django.apps import apps
from django.core.cache import caches
from django.db import DatabaseError


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
    exception_message = "database unavailable with sensitive connection details"
    mocker.patch(
        "django.db.backends.utils.CursorWrapper.execute",
        side_effect=DatabaseError(exception_message),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
        "security_cache": "ok",
    }
    assert exception_message not in response.content.decode()


def test_readiness_returns_503_when_security_cache_is_unavailable(client, mocker):
    exception_message = "redis unavailable with sensitive backend details"
    mocker.patch.object(
        caches["security"],
        "set",
        side_effect=OSError(exception_message),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ok",
        "security_cache": "unavailable",
    }
    assert exception_message not in response.content.decode()


def test_startup_reports_django_app_registry_initialization(client):
    response = client.get("/health/startup")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_returns_503_before_django_app_registry_is_ready(client, mocker):
    mocker.patch.object(apps, "ready", False)

    response = client.get("/health/startup")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/startup"])
@pytest.mark.parametrize(
    "method",
    ["head", "post", "put", "patch", "delete", "options", "trace"],
)
def test_health_endpoints_reject_unsupported_methods(client, path, method):
    response = getattr(client, method)(path)

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"
