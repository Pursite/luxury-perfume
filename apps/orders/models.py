import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.products.models import Product
from apps.users.models import Address


ZERO = Decimal("0.00")


class OrderManager(models.Manager):
    def create_waiting(self, *, user, source_address, idempotency_key, subtotal, shipping_amount, total):
        return self.create(
            user=user,
            source_address=source_address,
            source_address_uuid=source_address.pk,
            idempotency_key=idempotency_key,
            status=Order.Status.WAITING_FOR_PAYMENT,
            reservation_expires_at=timezone.now() + timedelta(minutes=15),
            subtotal=subtotal,
            shipping_amount=shipping_amount,
            total=total,
            customer_first_name=user.first_name,
            customer_last_name=user.last_name,
            customer_phone_number=user.phone_number or "",
            customer_email=user.email or "",
            shipping_title=source_address.title,
            shipping_full_address=source_address.full_address,
            shipping_postal_code=source_address.postal_code or "",
        )


class Order(models.Model):
    class Status(models.TextChoices):
        WAITING_FOR_PAYMENT = "waiting_for_payment", "Waiting for payment"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class CancellationReason(models.TextChoices):
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        RESERVATION_EXPIRED = "reservation_expired", "Reservation expired"

    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    source_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    source_address_uuid = models.UUIDField(editable=False)
    idempotency_key = models.UUIDField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.WAITING_FOR_PAYMENT)
    reservation_expires_at = models.DateTimeField()
    subtotal = models.DecimalField(max_digits=24, decimal_places=2, validators=[MinValueValidator(ZERO)])
    shipping_amount = models.DecimalField(max_digits=24, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)])
    total = models.DecimalField(max_digits=24, decimal_places=2, validators=[MinValueValidator(ZERO)])
    customer_first_name = models.CharField(max_length=50, blank=True)
    customer_last_name = models.CharField(max_length=50, blank=True)
    customer_phone_number = models.CharField(max_length=11, blank=True)
    customer_email = models.EmailField(blank=True)
    shipping_title = models.CharField(max_length=50)
    shipping_full_address = models.TextField()
    shipping_postal_code = models.CharField(max_length=10, blank=True)
    cancellation_reason = models.CharField(max_length=32, choices=CancellationReason.choices, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    late_payment_detected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderManager()

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("user", "idempotency_key"), name="orders_user_idempotency_key_unique"),
            models.UniqueConstraint(fields=("user",), condition=Q(status="waiting_for_payment"), name="orders_one_waiting_per_user"),
            models.CheckConstraint(condition=Q(status__in=("waiting_for_payment", "processing", "shipped", "delivered", "cancelled")), name="orders_valid_status"),
            models.CheckConstraint(condition=Q(subtotal__gte=0) & Q(shipping_amount__gte=0) & Q(total__gte=0), name="orders_nonnegative_amounts"),
            models.CheckConstraint(condition=Q(total=F("subtotal") + F("shipping_amount")), name="orders_total_matches_components"),
            models.CheckConstraint(condition=Q(status="waiting_for_payment", reservation_expires_at__isnull=False) | ~Q(status="waiting_for_payment"), name="orders_waiting_has_deadline"),
            models.CheckConstraint(condition=Q(reservation_expires_at__isnull=True) | Q(reservation_expires_at__gt=F("created_at")), name="orders_deadline_after_created"),
            models.CheckConstraint(condition=Q(status="cancelled", cancelled_at__isnull=False) | ~Q(status="cancelled"), name="orders_cancelled_has_timestamp"),
            models.CheckConstraint(condition=Q(late_payment_detected_at__isnull=True) | Q(status="cancelled"), name="orders_late_payment_only_cancelled"),
            models.CheckConstraint(condition=(
                Q(status="waiting_for_payment", processing_at__isnull=True, shipped_at__isnull=True, delivered_at__isnull=True, cancelled_at__isnull=True, cancellation_reason="", late_payment_detected_at__isnull=True)
                | Q(status="processing", processing_at__isnull=False, shipped_at__isnull=True, delivered_at__isnull=True, cancelled_at__isnull=True, cancellation_reason="")
                | Q(status="shipped", processing_at__isnull=False, shipped_at__isnull=False, delivered_at__isnull=True, cancelled_at__isnull=True, cancellation_reason="")
                | Q(status="delivered", processing_at__isnull=False, shipped_at__isnull=False, delivered_at__isnull=False, cancelled_at__isnull=True, cancellation_reason="")
                | Q(status="cancelled", processing_at__isnull=True, shipped_at__isnull=True, delivered_at__isnull=True, cancelled_at__isnull=False, cancellation_reason__in=("payment_failed", "reservation_expired"))
            ), name="orders_status_timestamps_consistent"),
        ]
        indexes = [
            models.Index(fields=("user", "-created_at"), name="orders_user_created_idx"),
            models.Index(fields=("status", "-created_at"), name="orders_status_created_idx"),
            models.Index(fields=("reservation_expires_at", "id"), condition=Q(status="waiting_for_payment"), name="orders_waiting_expiry_idx"),
        ]

    def __str__(self):
        return f"Order {self.uuid}"


class OrderItemManager(models.Manager):
    def create_from_product(self, *, order, product: Product, quantity: int):
        unit_price = Decimal(str(product.final_price))
        return self.create(
            order=order,
            product=product,
            product_uuid=product.uuid,
            product_name=product.name,
            product_sku=product.sku,
            unit_price=unit_price,
            quantity=quantity,
            line_total=unit_price * quantity,
        )


class OrderItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    product_uuid = models.UUIDField(editable=False)
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(max_digits=24, decimal_places=2, validators=[MinValueValidator(ZERO)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderItemManager()

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=("order", "product_uuid"), name="orders_item_unique_product_snapshot"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="orders_item_quantity_gte_1"),
            models.CheckConstraint(condition=Q(unit_price__gt=0) & Q(line_total__gte=0), name="orders_item_valid_amounts"),
            models.CheckConstraint(condition=Q(line_total=F("unit_price") * F("quantity")), name="orders_item_line_total_matches"),
        ]

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class StockReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"

    class ReleaseReason(models.TextChoices):
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        RESERVATION_EXPIRED = "reservation_expired", "Reservation expired"

    id = models.BigAutoField(primary_key=True)
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="reservation")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=32, blank=True, choices=ReleaseReason.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=("active", "consumed", "released")), name="orders_reservation_valid_status"),
            models.CheckConstraint(condition=Q(status="consumed", consumed_at__isnull=False, released_at__isnull=True, release_reason="") | ~Q(status="consumed"), name="orders_reservation_consumed_fields"),
            models.CheckConstraint(condition=Q(status="released", released_at__isnull=False, consumed_at__isnull=True, release_reason__in=("payment_failed", "reservation_expired")) | ~Q(status="released"), name="orders_reservation_released_fields"),
            models.CheckConstraint(condition=Q(status="active", consumed_at__isnull=True, released_at__isnull=True, release_reason="") | ~Q(status="active"), name="orders_reservation_active_fields"),
        ]

    def __str__(self):
        return f"Reservation for {self.order_item}"
