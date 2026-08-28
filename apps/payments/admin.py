from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm

from apps.payments.exceptions import RefundNotEligibleError
from apps.payments.models import Payment, Refund
from apps.payments.services.reconciliation import rearm_manual_review_payment
from apps.payments.services.refunds import record_manual_refund_completion
from apps.payments.tasks import execute_refund_task, reconcile_payment_task


class RefundActionForm(ActionForm):
    provider_refund_id = forms.CharField(
        required=False,
        max_length=255,
        label="External refund reference",
    )
    confirm_external_completion = forms.BooleanField(
        required=False,
        label="I confirm this refund was completed externally",
    )


class ImmutableFinancialAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Payment)
class PaymentAdmin(ImmutableFinancialAdmin):
    list_display = ("uuid", "order_uuid", "owner", "provider", "status", "amount", "currency", "verified_at", "created_at")
    list_filter = ("provider", "status", "created_at", "verified_at")
    search_fields = ("uuid", "order__uuid", "provider_receipt_id", "provider_transaction_id")
    date_hierarchy = "created_at"
    actions = ("request_reconciliation",)
    safe_fields = (
        "uuid", "order", "provider", "status", "amount", "currency",
        "provider_requested_at", "redirect_ready_at", "provider_paid_at",
        "verified_at", "failed_at", "manual_review_at", "applied_to_order_at",
        "created_at", "updated_at",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("order__user")
        if not request.user.is_superuser:
            queryset = queryset.filter(order__user__is_staff=False, order__user__is_superuser=False)
        return queryset

    def _has_owner_access(self, request, obj):
        return request.user.is_superuser or not (
            obj and (obj.order.user.is_staff or obj.order.user.is_superuser)
        )

    def has_view_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_change_permission(request, obj)

    def get_fields(self, request, obj=None):
        if request.user.is_superuser:
            return self.get_readonly_fields(request, obj)
        return self.safe_fields

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("request_reconciliation", None)
        return actions

    @admin.display(description="Order UUID", ordering="order__uuid")
    def order_uuid(self, obj):
        return obj.order.uuid

    @admin.display(description="Owner", ordering="order__user")
    def owner(self, obj):
        return obj.order.user

    @admin.action(description="Request payment reconciliation")
    def request_reconciliation(self, request, queryset):
        count = 0
        for payment_id, payment_status in queryset.values_list("pk", "status"):
            if payment_status == Payment.Status.MANUAL_REVIEW:
                rearm_manual_review_payment(payment_id=payment_id, requested_by=request.user)
            elif payment_status not in Payment.RECONCILABLE_STATUSES:
                continue
            reconcile_payment_task.delay(payment_id)
            count += 1
        self.message_user(request, f"{count} payment(s) queued for reconciliation.", level=messages.SUCCESS)


@admin.register(Refund)
class RefundAdmin(ImmutableFinancialAdmin):
    list_display = ("uuid", "payment_uuid", "provider", "reason", "status", "amount", "currency", "created_at")
    list_filter = ("provider", "reason", "status", "created_at")
    search_fields = ("uuid", "payment__uuid", "provider_receipt_id", "provider_refund_id")
    date_hierarchy = "created_at"
    actions = ("retry_manual_review", "record_external_completion")
    action_form = RefundActionForm
    safe_fields = (
        "uuid", "payment", "provider", "reason", "status", "amount",
        "currency", "processing_at", "refunded_at", "manual_review_at",
        "last_failed_at", "attempt_count", "next_retry_at", "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("payment__order__user")
        if not request.user.is_superuser:
            queryset = queryset.filter(payment__order__user__is_staff=False, payment__order__user__is_superuser=False)
        return queryset

    def _has_owner_access(self, request, obj):
        return request.user.is_superuser or not (
            obj and (obj.payment.order.user.is_staff or obj.payment.order.user.is_superuser)
        )

    def has_view_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._has_owner_access(request, obj) and super().has_change_permission(request, obj)

    def get_fields(self, request, obj=None):
        if request.user.is_superuser:
            return self.get_readonly_fields(request, obj)
        return self.safe_fields

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("retry_manual_review", None)
            actions.pop("record_external_completion", None)
        return actions

    @admin.display(description="Payment UUID", ordering="payment__uuid")
    def payment_uuid(self, obj):
        return obj.payment.uuid

    @admin.action(description="Retry manual-review refunds")
    def retry_manual_review(self, request, queryset):
        count = 0
        for refund_id in queryset.filter(status=Refund.Status.MANUAL_REVIEW).values_list("pk", flat=True):
            execute_refund_task.delay(refund_id)
            count += 1
        self.message_user(request, f"{count} refund(s) queued for retry.", level=messages.SUCCESS)

    @admin.action(description="Record one externally completed refund")
    def record_external_completion(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one refund.", level=messages.ERROR)
            return
        try:
            refund = record_manual_refund_completion(
                refund_id=queryset.values_list("pk", flat=True).get(),
                completed_by=request.user,
                provider_refund_id=request.POST.get("provider_refund_id", ""),
                confirmed=request.POST.get("confirm_external_completion") == "on",
            )
        except RefundNotEligibleError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        self.message_user(
            request,
            f"Refund {refund.uuid} recorded as externally completed.",
            level=messages.SUCCESS,
        )
