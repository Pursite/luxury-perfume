from django.contrib.admin import AdminSite
from django.urls import include, path

from apps.backoffice import views
from apps.backoffice.permissions import get_access


class BackofficeAdminSite(AdminSite):
    site_header = "Luxury Perfume Administration"
    site_title = "Luxury Perfume Admin"
    index_template = "backoffice/admin_index.html"

    def get_urls(self):
        routes = [
            path("", self.admin_view(views.dashboard), name="dashboard"),
            path("inventory/", self.admin_view(views.inventory), name="inventory"),
            path("orders/<uuid:order_uuid>/summary/", self.admin_view(views.order_summary), name="order_summary"),
            path("customers/<uuid:customer_id>/", self.admin_view(views.customer_detail), name="customer_detail"),
        ]
        return [path("backoffice/", include((routes, "backoffice"))), *super().get_urls()]

    def index(self, request, extra_context=None):
        return super().index(
            request,
            extra_context={"backoffice_access": get_access(request.user), **(extra_context or {})},
        )
