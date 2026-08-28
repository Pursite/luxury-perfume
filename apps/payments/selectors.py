from django.db.models import Prefetch

from apps.payments.models import Payment, Refund


def get_owner_payment_queryset(*, user):
    return Payment.objects.filter(order__user=user).select_related("order").prefetch_related(
        Prefetch("refunds", queryset=Refund.objects.order_by("id"), to_attr="safe_refunds")
    )

