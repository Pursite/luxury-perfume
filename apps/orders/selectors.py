from django.db.models import Prefetch

from apps.orders.models import Order, OrderItem


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
