import pytest
from django.contrib.auth.models import Group, Permission

from apps.users.tests.factories import UserFactory


@pytest.fixture
def staff_client(client):
    def login(*permissions):
        staff = UserFactory(is_staff=True)
        if permissions:
            group = Group.objects.create(name=f"Store operators {staff.pk}")
            for permission in permissions:
                app_label, codename = permission.split(".")
                group.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
            staff.groups.add(group)
        client.force_login(staff)
        return client

    return login
