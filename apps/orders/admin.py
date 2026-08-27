from django.contrib import admin, messages

from apps.orders.models import Order, OrderItem
from apps.orders.services.transitions import (
    InvalidOrderTransitionError,
    mark_order_delivered,
    mark_order_shipped,
)


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
    list_display = ("uuid", "user", "status", "total", "reservation_expires_at", "created_at")
    list_filter = ("status", "created_at")
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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected processing orders as shipped")
    def mark_selected_shipped(self, request, queryset):
        changed = 0
        for order_id in queryset.filter(status=Order.Status.PROCESSING).values_list("pk", flat=True):
            try:
                mark_order_shipped(order_id=order_id)
            except InvalidOrderTransitionError:
                continue
            changed += 1
        self.message_user(request, f"{changed} order(s) marked as shipped.", level=messages.SUCCESS)

    @admin.action(description="Mark selected shipped orders as delivered")
    def mark_selected_delivered(self, request, queryset):
        changed = 0
        for order_id in queryset.filter(status=Order.Status.SHIPPED).values_list("pk", flat=True):
            try:
                mark_order_delivered(order_id=order_id)
            except InvalidOrderTransitionError:
                continue
            changed += 1
        self.message_user(request, f"{changed} order(s) marked as delivered.", level=messages.SUCCESS)
