import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied

from apps.lib.permissions import IsProfileComplete
from apps.users.models import Address
from apps.users.tests.factories import UserFactory
from apps.users.permissions import CookieAuthOriginPermission


@pytest.mark.django_db
def test_profile_completion_permission_is_opt_in_and_requires_complete_customer_data():
    user = UserFactory(email="customer@example.com")
    request = APIRequestFactory().post("/")
    request.user = user
    permission = IsProfileComplete()

    assert permission.has_permission(request, None) is False

    Address.objects.create(
        user=user,
        title="Home",
        full_address="Test address",
    )

    assert permission.has_permission(request, None) is True


@pytest.mark.parametrize("origin", [None, "null", "https://api.exonplus.ir", "https://attacker.example"])
def test_cookie_auth_origin_permission_rejects_untrusted_origins(origin):
    request = APIRequestFactory().post(
        "/",
        HTTP_ORIGIN=origin,
    )

    with pytest.raises(PermissionDenied):
        CookieAuthOriginPermission().has_permission(request, None)


@override_settings(CORS_ALLOWED_ORIGINS=["https://www.exonplus.ir"])
def test_cookie_auth_origin_permission_accepts_storefront_and_options():
    permission = CookieAuthOriginPermission()
    storefront_request = APIRequestFactory().post(
        "/",
        HTTP_ORIGIN="https://www.exonplus.ir",
    )
    assert permission.has_permission(storefront_request, None) is True

    preflight = APIRequestFactory().options(
        "/",
        HTTP_ORIGIN="https://attacker.example",
    )
    assert permission.has_permission(preflight, None) is True


@pytest.mark.django_db
def test_trusted_storefront_preflight_receives_credentialed_cors_headers(settings):
    settings.CORS_ALLOWED_ORIGINS = ["https://www.exonplus.ir"]
    settings.CORS_ALLOW_CREDENTIALS = True
    response = APIClient().options(
        reverse("users:login_password"),
        HTTP_ORIGIN="https://www.exonplus.ir",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response["Access-Control-Allow-Origin"] == "https://www.exonplus.ir"
    assert response["Access-Control-Allow-Credentials"] == "true"
