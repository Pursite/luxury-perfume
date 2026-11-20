from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.http import require_safe

from apps.backoffice.forms import DashboardDateForm, InventoryFilterForm
from apps.backoffice.permissions import get_access
from apps.backoffice.selectors import (
    get_dashboard_data,
    get_low_stock_products,
    get_order_attention,
    get_order_summary,
    get_visible_customer,
)
from apps.orders.selectors import get_user_orders_queryset


def _render(request, template, *, access, title, section="", status=200, **context):
    request.current_app = admin.site.name
    return TemplateResponse(
        request,
        f"backoffice/{template}.html",
        {**admin.site.each_context(request), "access": access, "title": title, "section": section, **context},
        status=status,
    )


@require_safe
def dashboard(request):
    access = get_access(request.user)
    if not access.dashboard:
        raise PermissionDenied

    form = DashboardDateForm(request.GET if "start" in request.GET or "end" in request.GET else None)
    dates = form.initial
    if form.is_bound:
        dates = form.cleaned_data if form.is_valid() else None
    context = {
        "form": form,
        "access": access,
        "title": "Store dashboard",
        "section": "dashboard",
        "store_timezone": timezone.get_default_timezone_name(),
        "presets": form.presets(dates),
    }
    if access.orders:
        context["attention"] = get_order_attention(request.user)
    if dates is None:
        return _render(request, "dashboard", **context, status=400)
    return _render(
        request, "dashboard", **context,
        metrics=get_dashboard_data(user=request.user, access=access, **dates),
    )


@require_safe
def order_summary(request, order_uuid):
    access = get_access(request.user)
    if not access.orders:
        raise PermissionDenied
    order = get_order_summary(request.user, order_uuid)
    return _render(request, "order_summary", access=access, title="Order Summary", section="order", order=order)


@require_safe
def customer_detail(request, customer_id):
    access = get_access(request.user)
    if not (access.customers and access.orders):
        raise PermissionDenied
    customer = get_visible_customer(request.user, customer_id)
    orders = get_user_orders_queryset(user=customer).only("id", "uuid", "status", "total", "created_at")
    page = Paginator(orders, 50).get_page(request.GET.get("page"))
    return _render(request, "customer_detail", access=access, title="Customer history", section="customer", customer=customer, page=page)


@require_safe
def inventory(request):
    access = get_access(request.user)
    if not access.inventory:
        raise PermissionDenied
    form = InventoryFilterForm(request.GET if "threshold" in request.GET else None)
    context = {"form": form, "access": access, "title": "Low-stock inventory", "section": "inventory"}
    if form.is_bound and not form.is_valid():
        return _render(request, "inventory", **context, status=400)
    threshold = form.cleaned_data["threshold"] if form.is_bound else form["threshold"].initial
    page = Paginator(get_low_stock_products(threshold), 50).get_page(request.GET.get("page"))
    return _render(request, "inventory", **context, page=page)
