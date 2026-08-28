import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REDIRECT_READY = "redirect_ready", "Redirect ready"
        VERIFYING = "verifying", "Verifying"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"
        MANUAL_REVIEW = "manual_review", "Manual review"

    OPEN_STATUSES = (Status.PENDING, Status.REDIRECT_READY, Status.VERIFYING, Status.MANUAL_REVIEW)
    RECONCILABLE_STATUSES = (Status.PENDING, Status.REDIRECT_READY, Status.VERIFYING)

    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=32)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=24, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="IRT", editable=False)
    captured_amount = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True)
    captured_currency = models.CharField(max_length=3, null=True, blank=True)
    provider_session_id = models.CharField(max_length=255, null=True, blank=True)
    provider_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    provider_receipt_id = models.CharField(max_length=255, null=True, blank=True)
    idempotency_key = models.UUIDField(unique=True)
    initiator_ip = models.GenericIPAddressField(null=True, blank=True)
    initiator_user_agent = models.CharField(max_length=512, blank=True)
    initiator_request_id = models.CharField(max_length=32)
    first_callback_ip = models.GenericIPAddressField(null=True, blank=True)
    first_callback_at = models.DateTimeField(null=True, blank=True)
    last_callback_at = models.DateTimeField(null=True, blank=True)
    callback_count = models.PositiveIntegerField(default=0)
    provider_requested_at = models.DateTimeField(null=True, blank=True)
    redirect_ready_at = models.DateTimeField(null=True, blank=True)
    operation_token = models.UUIDField(null=True, blank=True)
    operation_started_at = models.DateTimeField(null=True, blank=True)
    provider_paid_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    manual_review_at = models.DateTimeField(null=True, blank=True)
    applied_to_order_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)
    reconciliation_attempts = models.PositiveIntegerField(default=0)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    next_reconciliation_at = models.DateTimeField(null=True, blank=True)
    audit_scrubbed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payments_payment_amount_positive"),
            models.CheckConstraint(condition=Q(captured_amount__isnull=True) | Q(captured_amount__gt=0), name="payments_capture_amount_positive"),
            models.CheckConstraint(condition=Q(currency="IRT"), name="payments_payment_currency_irt"),
            models.CheckConstraint(condition=Q(captured_currency__isnull=True) | Q(captured_currency__regex=r"^[A-Z]{3}$"), name="payments_capture_currency_code"),
            models.CheckConstraint(condition=Q(status__in=("pending", "redirect_ready", "verifying", "verified", "failed", "manual_review")), name="payments_payment_valid_status"),
            models.CheckConstraint(condition=(Q(operation_token__isnull=True, operation_started_at__isnull=True) | Q(operation_token__isnull=False, operation_started_at__isnull=False)), name="payments_operation_fields_paired"),
            models.CheckConstraint(condition=(~Q(status__in=("redirect_ready", "verifying", "verified")) | Q(provider_session_id__isnull=False, redirect_ready_at__isnull=False)), name="payments_session_state_fields"),
            models.CheckConstraint(condition=(~Q(status="verifying") | Q(operation_token__isnull=False, operation_started_at__isnull=False)), name="payments_verifying_has_operation"),
            models.CheckConstraint(
                condition=(
                    ~Q(status="verified")
                    | Q(
                        verified_at__isnull=False,
                        captured_amount__gt=0,
                        captured_currency__regex=r"^[A-Z]{3}$",
                        provider_session_id__isnull=False,
                        provider_transaction_id__isnull=False,
                        failed_at__isnull=True,
                        manual_review_at__isnull=True,
                    )
                ),
                name="payments_verified_fields",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="failed")
                    | (
                        Q(failed_at__isnull=False)
                        & ~Q(failure_code="")
                        & Q(captured_amount__isnull=True, captured_currency__isnull=True, verified_at__isnull=True, manual_review_at__isnull=True)
                    )
                ),
                name="payments_failed_fields",
            ),
            models.CheckConstraint(condition=(~Q(status="manual_review") | (Q(manual_review_at__isnull=False) & ~Q(failure_code=""))), name="payments_review_fields"),
            models.CheckConstraint(
                condition=(
                    ~Q(status="manual_review")
                    | Q(
                        next_reconciliation_at__isnull=True,
                        operation_token__isnull=True,
                        operation_started_at__isnull=True,
                    )
                ),
                name="payments_review_has_no_automatic_work",
            ),
            models.CheckConstraint(condition=(Q(applied_to_order_at__isnull=True) | Q(status="verified")), name="payments_applied_only_verified"),
            models.CheckConstraint(
                condition=(
                    Q(callback_count=0, first_callback_at__isnull=True, last_callback_at__isnull=True)
                    | Q(callback_count__gt=0, first_callback_at__isnull=False, last_callback_at__isnull=False)
                ),
                name="payments_callback_fields",
            ),
            models.UniqueConstraint(fields=("provider", "provider_session_id"), condition=Q(provider_session_id__isnull=False), name="payments_provider_session_unique"),
            models.UniqueConstraint(fields=("provider", "provider_transaction_id"), condition=Q(provider_transaction_id__isnull=False), name="payments_provider_transaction_unique"),
            models.UniqueConstraint(fields=("order",), condition=Q(applied_to_order_at__isnull=False), name="payments_one_applied_per_order"),
            models.UniqueConstraint(fields=("order",), condition=Q(status__in=("pending", "redirect_ready", "verifying", "manual_review")), name="payments_one_open_per_order"),
        ]
        indexes = [
            models.Index(fields=("order", "-created_at"), name="payments_order_created_idx"),
            models.Index(fields=("status", "-created_at"), name="payments_status_created_idx"),
            models.Index(fields=("next_reconciliation_at", "id"), condition=Q(status__in=("pending", "redirect_ready", "verifying")), name="payments_reconcile_due_idx"),
            models.Index(fields=("created_at", "id"), condition=Q(audit_scrubbed_at__isnull=True), name="payments_audit_unscrub_idx"),
        ]

    def __str__(self):
        return f"Payment {self.uuid}"


class Refund(models.Model):
    class Reason(models.TextChoices):
        LATE_PAYMENT = "late_payment", "Late payment"
        DUPLICATE_PAYMENT = "duplicate_payment", "Duplicate payment"
        AMOUNT_MISMATCH = "amount_mismatch", "Amount mismatch"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        REFUNDED = "refunded", "Refunded"
        MANUAL_REVIEW = "manual_review", "Manual review"

    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    provider = models.CharField(max_length=32)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=24, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="IRT", editable=False)
    provider_refund_id = models.CharField(max_length=255, null=True, blank=True)
    provider_receipt_id = models.CharField(max_length=255, null=True, blank=True)
    operation_token = models.UUIDField(null=True, blank=True)
    operation_started_at = models.DateTimeField(null=True, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    manual_review_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="completed_payment_refunds")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payments_refund_amount_positive"),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="payments_refund_currency_code"),
            models.CheckConstraint(condition=Q(reason__in=("late_payment", "duplicate_payment", "amount_mismatch")), name="payments_refund_valid_reason"),
            models.CheckConstraint(condition=Q(status__in=("pending", "processing", "refunded", "manual_review")), name="payments_refund_valid_status"),
            models.CheckConstraint(condition=(Q(operation_token__isnull=True, operation_started_at__isnull=True) | Q(operation_token__isnull=False, operation_started_at__isnull=False)), name="payments_refund_operation_pair"),
            models.CheckConstraint(condition=(~Q(status="processing") | Q(processing_at__isnull=False, operation_token__isnull=False, operation_started_at__isnull=False)), name="payments_refund_processing"),
            models.CheckConstraint(condition=(~Q(status="refunded") | (Q(refunded_at__isnull=False) & (Q(provider_refund_id__isnull=False) | Q(completed_by__isnull=False)))), name="payments_refunded_evidence"),
            models.CheckConstraint(condition=(~Q(status="manual_review") | (Q(manual_review_at__isnull=False) & ~Q(failure_code=""))), name="payments_refund_review"),
            models.UniqueConstraint(fields=("payment",), name="payments_one_refund_per_payment"),
            models.UniqueConstraint(fields=("provider", "provider_refund_id"), condition=Q(provider_refund_id__isnull=False), name="payments_provider_refund_unique"),
        ]
        indexes = [
            models.Index(fields=("status", "-created_at"), name="payments_refund_status_idx"),
            models.Index(fields=("next_retry_at", "id"), condition=Q(status__in=("pending", "processing")), name="payments_refund_retry_idx"),
        ]

    def __str__(self):
        return f"Refund {self.uuid}"
