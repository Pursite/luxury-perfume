from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.orders.models import Order, OrderItem
from apps.orders.selectors import get_order_attention_conditions
from apps.orders.services.transitions import (
    InvalidOrderTransitionError,
    mark_order_delivered,
    mark_order_shipped,
)
from apps.users.models import CustomUser


class OrderAttentionFilter(admin.SimpleListFilter):
    title = "operational attention"
    parameter_name = "attention"

    def lookups(self, request, model_admin):
        return (
            ("to_ship", "Ready to ship"),
            ("in_transit", "Awaiting delivery"),
            ("overdue", "Overdue payment reservations"),
        )

    def queryset(self, request, queryset):
        condition = get_order_attention_conditions().get(self.value())
        return queryset.filter(condition) if condition is not None else queryset


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product", "product_uuid", "product_name", "product_sku", "unit_price",
        "quantity", "line_total", "reservation_status", "reservation_consumed_at",
        "reservation_released_at", "reservation_release_reason", "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Reservation status")
    def reservation_status(self, obj):
        return obj.reservation.status

    @admin.display(description="Reservation consumed")
    def reservation_consumed_at(self, obj):
        return obj.reservation.consumed_at

    @admin.display(description="Reservation released")
    def reservation_released_at(self, obj):
        return obj.reservation.released_at

    @admin.display(description="Reservation release reason")
    def reservation_release_reason(self, obj):
        return obj.reservation.release_reason


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    change_form_template = "backoffice/order_change_form.html"
    list_display = ("uuid", "user", "status", "total", "reservation_expires_at", "created_at")
    list_filter = (OrderAttentionFilter, "status", "created_at")
    search_fields = ("uuid", "user__phone_number", "user__username", "customer_phone_number", "customer_email")
    list_select_related = ("user", "source_address")
    date_hierarchy = "created_at"
    inlines = (OrderItemInline,)
    actions = ("mark_selected_shipped", "mark_selected_delivered")
    readonly_fields = (
        "uuid", "user", "source_address", "source_address_uuid", "idempotency_key", "status",
        "reservation_expires_at", "subtotal", "shipping_amount", "total",
        "customer_first_name", "customer_last_name", "customer_phone_number", "customer_email",
        "shipping_title", "shipping_full_address", "shipping_postal_code", "cancellation_reason",
        "processing_at", "shipped_at", "delivered_at", "cancelled_at", "late_payment_detected_at",
        "created_at", "updated_at",
    )
    fields = readonly_fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user", "source_address")
        if not request.user.is_superuser:
            queryset = queryset.filter(user__is_staff=False, user__is_superuser=False)
        return queryset

    def _has_owner_access(self, request, obj):
        return request.user.is_superuser or not (obj and (obj.user.is_staff or obj.user.is_superuser))

    def has_view_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(permissions=("change",), description="Mark selected processing orders as shipped")
    def mark_selected_shipped(self, request, queryset):
        changed = self._apply_fulfillment(
            request, queryset, Order.Status.PROCESSING, mark_order_shipped, "Order marked as shipped.",
        )
        self.message_user(request, f"{changed} order(s) marked as shipped.", level=messages.SUCCESS)

    @admin.action(permissions=("change",), description="Mark selected shipped orders as delivered")
    def mark_selected_delivered(self, request, queryset):
        changed = self._apply_fulfillment(
            request, queryset, Order.Status.SHIPPED, mark_order_delivered, "Order marked as delivered.",
        )
        self.message_user(request, f"{changed} order(s) marked as delivered.", level=messages.SUCCESS)

    def _apply_fulfillment(self, request, queryset, status, transition, audit_message):
        if not self.admin_site.has_permission(request) or not self.has_change_permission(request):
            raise PermissionDenied

        changed = 0
        selection = queryset.filter(status=status).values_list("pk", "user_id")
        for order_id, owner_id in selection.iterator():
            try:
                with transaction.atomic():
                    if not request.user.is_superuser:
                        # Match checkout's user-before-order lock order.
                        owner_is_customer = CustomUser.objects.select_for_update().filter(
                            pk=owner_id, is_staff=False, is_superuser=False,
                        ).exists()
                        if not owner_is_customer:
                            continue
                    order = transition(order_id=order_id)
                    self.log_change(request, order, audit_message)
            except InvalidOrderTransitionError:
                continue
            changed += 1
        return changed
