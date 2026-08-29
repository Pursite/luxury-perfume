from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from apps.lib.sms.phone import mask_iranian_mobile
from apps.notifications.models import SmsDelivery
from apps.notifications.services.delivery import rearm_manual_delivery


@admin.register(SmsDelivery)
class SmsDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "uuid", "order_uuid", "event_type", "recipient_type", "masked_recipient",
        "provider", "status", "attempt_count", "created_at",
    )
    list_filter = ("event_type", "recipient_type", "provider", "status", "created_at")
    search_fields = ("uuid", "order__uuid")
    date_hierarchy = "created_at"
    list_select_related = ("order", "order__user")
    actions = ("rearm_selected_manual_review",)
    readonly_fields = (
        "id", "uuid", "order", "event_type", "recipient_type", "masked_recipient",
        "provider", "status", "attempt_count", "provider_message_id", "operation_token",
        "operation_started_at", "last_attempt_at", "next_retry_at", "sent_at", "failed_at",
        "manual_review_at", "failure_code", "audit_scrubbed_at", "created_at", "updated_at",
    )
    fields = readonly_fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("order__user")
        if not request.user.is_superuser:
            queryset = queryset.filter(order__user__is_staff=False, order__user__is_superuser=False)
        return queryset

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser and (obj.order.user.is_staff or obj.order.user.is_superuser):
            return False
        return super().has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser and (obj.order.user.is_staff or obj.order.user.is_superuser):
            return False
        return super().has_view_permission(request, obj)

    @admin.display(description="Order UUID", ordering="order__uuid")
    def order_uuid(self, obj):
        return obj.order.uuid

    @admin.display(description="Recipient")
    def masked_recipient(self, obj):
        return mask_iranian_mobile(obj.recipient_phone)

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.is_superuser:
            fields.remove("provider_message_id")
        return fields

    @admin.action(description="Re-arm selected manual-review SMS deliveries")
    def rearm_selected_manual_review(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can re-arm SMS deliveries.", level=messages.ERROR)
            return
        if request.POST.get("confirm_sms_retry") != "yes":
            self.message_user(
                request,
                "Retry was not performed. Re-submit with explicit retry confirmation.",
                level=messages.WARNING,
            )
            return
        rearmed = 0
        for delivery_id in queryset.filter(status=SmsDelivery.Status.MANUAL_REVIEW).values_list("pk", flat=True):
            try:
                delivery = rearm_manual_delivery(delivery_id=delivery_id)
            except ValueError:
                continue
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=ContentType.objects.get_for_model(SmsDelivery).pk,
                object_id=str(delivery.pk),
                object_repr=str(delivery.uuid),
                action_flag=LogEntry.ActionFlag.CHANGE,
                change_message="SMS delivery manually re-armed after explicit confirmation.",
            )
            rearmed += 1
        self.message_user(request, f"{rearmed} SMS delivery record(s) re-armed.", level=messages.SUCCESS)
