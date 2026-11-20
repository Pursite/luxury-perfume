from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.orders.models import Order, OrderItem


def get_order_attention_conditions():
    return {
        "to_ship": Q(status=Order.Status.PROCESSING),
        "in_transit": Q(status=Order.Status.SHIPPED),
        "overdue": Q(status=Order.Status.WAITING_FOR_PAYMENT, reservation_expires_at__lte=timezone.now()),
    }


def get_user_orders_queryset(*, user):
    return Order.objects.filter(user=user).order_by("-created_at", "-id")


def get_user_order_detail_queryset(*, user):
    return (
        get_user_orders_queryset(user=user)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("reservation").order_by("id"),
            )
        )
    )
