import pytest
from rest_framework.test import APIRequestFactory

from apps.lib.permissions import IsProfileComplete
from apps.users.models import Address
from apps.users.tests.factories import UserFactory


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
