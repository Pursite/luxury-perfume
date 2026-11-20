from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class BackofficeConfig(AppConfig):
    name = "apps.backoffice"


class BackofficeAdminConfig(AdminConfig):
    default_site = "apps.backoffice.admin_site.BackofficeAdminSite"
