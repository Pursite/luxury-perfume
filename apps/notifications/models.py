import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class SmsDelivery(models.Model):
    class EventType(models.TextChoices):
        CUSTOMER_ORDER_CONFIRMED = "CUSTOMER_ORDER_CONFIRMED", "Customer order confirmed"
        OWNER_ORDER_PROCESSING = "OWNER_ORDER_PROCESSING", "Owner order processing"
        CUSTOMER_ORDER_SHIPPED = "CUSTOMER_ORDER_SHIPPED", "Customer order shipped"

    class RecipientType(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        OWNER = "OWNER", "Owner"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENDING = "SENDING", "Sending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        MANUAL_REVIEW = "MANUAL_REVIEW", "Manual review"

    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="sms_deliveries")
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_sms_deliveries",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    recipient_type = models.CharField(max_length=8, choices=RecipientType.choices)
    recipient_phone = models.CharField(max_length=11, null=True, blank=True)
    provider = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)
    operation_token = models.UUIDField(null=True, blank=True, editable=False)
    operation_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    manual_review_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    audit_scrubbed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("order", "event_type"),
                condition=Q(recipient_type="CUSTOMER"),
                name="notifications_customer_order_event_unique",
            ),
            models.UniqueConstraint(
                fields=("order", "event_type", "recipient_user"),
                condition=Q(event_type="OWNER_ORDER_PROCESSING"),
                name="notifications_owner_order_recipient_unique",
            ),
            models.UniqueConstraint(
                fields=("provider", "provider_message_id"),
                condition=Q(provider_message_id__isnull=False),
                name="notifications_provider_message_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(event_type="CUSTOMER_ORDER_CONFIRMED", recipient_type="CUSTOMER")
                    | Q(event_type="OWNER_ORDER_PROCESSING", recipient_type="OWNER")
                    | Q(event_type="CUSTOMER_ORDER_SHIPPED", recipient_type="CUSTOMER")
                ),
                name="notifications_event_recipient_match",
            ),
            models.CheckConstraint(
                condition=(
                    Q(event_type="OWNER_ORDER_PROCESSING", recipient_user__isnull=False)
                    | Q(
                        event_type__in=("CUSTOMER_ORDER_CONFIRMED", "CUSTOMER_ORDER_SHIPPED"),
                        recipient_user__isnull=True,
                    )
                ),
                name="notifications_event_recipient_user_match",
            ),
            models.CheckConstraint(
                condition=Q(recipient_phone__isnull=True) | Q(recipient_phone__regex=r"^09[0-9]{9}$"),
                name="notifications_valid_recipient_phone",
            ),
            models.CheckConstraint(
                condition=Q(provider_message_id__isnull=True) | Q(provider_message_id__gt=""),
                name="notifications_nonblank_provider_message_id",
            ),
            models.CheckConstraint(
                condition=Q(failure_code__regex=r"^[A-Za-z0-9_-]*$"),
                name="notifications_safe_failure_code",
            ),
            models.CheckConstraint(
                condition=(
                    Q(operation_token__isnull=True, operation_started_at__isnull=True)
                    | Q(operation_token__isnull=False, operation_started_at__isnull=False)
                ),
                name="notifications_operation_lease_paired",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="PENDING", next_retry_at__isnull=False,
                        operation_token__isnull=True, operation_started_at__isnull=True,
                        sent_at__isnull=True, failed_at__isnull=True, manual_review_at__isnull=True,
                    )
                    | Q(
                        status="SENDING", next_retry_at__isnull=False,
                        operation_token__isnull=False, operation_started_at__isnull=False,
                        last_attempt_at__isnull=False, attempt_count__gt=0,
                        sent_at__isnull=True, failed_at__isnull=True, manual_review_at__isnull=True,
                    )
                    | Q(
                        status="SENT", next_retry_at__isnull=True,
                        operation_token__isnull=True, operation_started_at__isnull=True,
                        sent_at__isnull=False, provider_message_id__gt="",
                        failed_at__isnull=True, manual_review_at__isnull=True,
                    )
                    | Q(
                        status="FAILED", next_retry_at__isnull=True,
                        operation_token__isnull=True, operation_started_at__isnull=True,
                        failed_at__isnull=False, failure_code__gt="",
                        sent_at__isnull=True, manual_review_at__isnull=True,
                    )
                    | Q(
                        status="MANUAL_REVIEW", next_retry_at__isnull=True,
                        operation_token__isnull=True, operation_started_at__isnull=True,
                        manual_review_at__isnull=False, failure_code__gt="",
                        sent_at__isnull=True, failed_at__isnull=True,
                    )
                ),
                name="notifications_status_lifecycle_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=("SENT", "FAILED"))
                    | Q(recipient_phone__regex=r"^09[0-9]{9}$")
                ),
                name="notifications_actionable_phone_required",
            ),
            models.CheckConstraint(
                condition=Q(audit_scrubbed_at__isnull=True)
                | Q(recipient_phone__isnull=True, status__in=("SENT", "FAILED")),
                name="notifications_scrubbed_is_terminal",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "-created_at"), name="notifications_status_created_idx"),
            models.Index(
                fields=("next_retry_at", "id"),
                condition=Q(status__in=("PENDING", "SENDING")),
                name="notifications_due_idx",
            ),
            models.Index(
                fields=("created_at", "id"),
                condition=Q(status__in=("SENT", "FAILED"), recipient_phone__isnull=False),
                name="notifications_scrub_idx",
            ),
        ]
