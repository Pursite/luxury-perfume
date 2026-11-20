from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import reduce
from operator import or_

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.selectors import get_order_attention_conditions
from apps.payments.models import Payment
from apps.products.models import Product
from apps.users.models import CustomUser


def get_visible_orders(user):
    orders = Order.objects.all()
    if user.is_superuser:
        return orders
    return orders.filter(user__is_staff=False, user__is_superuser=False)


def get_visible_customer(user, customer_id):
    customers = CustomUser.objects.all()
    if not user.is_superuser:
        customers = customers.filter(is_staff=False, is_superuser=False)
    return get_object_or_404(customers, pk=customer_id)


def get_order_summary(user, order_uuid):
    return get_object_or_404(get_visible_orders(user).prefetch_related("items"), uuid=order_uuid)


def get_low_stock_products(threshold):
    return (
        Product.objects.filter(is_active=True, stock__lte=threshold)
        .only("id", "name", "sku", "stock")
        .order_by("stock", "name", "pk")
    )


def get_order_attention(user):
    conditions = get_order_attention_conditions()
    orders = get_visible_orders(user).filter(reduce(or_, conditions.values()))
    counts = orders.aggregate(**{
        name: Count("pk", filter=condition) for name, condition in conditions.items()
    })
    return {"total": sum(counts.values()), **counts}


def get_dashboard_data(*, user, access, start, end):
    business_tz = timezone.get_default_timezone()
    period = (
        datetime.combine(start, time.min, tzinfo=business_tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=business_tz),
    )
    data = {}
    if access.orders:
        orders = get_visible_orders(user).filter(created_at__gte=period[0], created_at__lt=period[1])
        data["orders"] = {"total": orders.count()}
        data["recent_orders"] = orders.only("id", "uuid", "status", "total", "created_at")[:10]
    if access.customers:
        data["new_customers"] = CustomUser.objects.filter(
            is_staff=False, is_superuser=False, created_at__gte=period[0], created_at__lt=period[1],
        ).count()
    if access.sales:
        captures = Payment.objects.filter(
            order__in=get_visible_orders(user),
            status=Payment.Status.VERIFIED,
            applied_to_order_at__isnull=False,
            currency="IRT",
            captured_currency="IRT",
            verified_at__gte=period[0],
            verified_at__lt=period[1],
        )
        data["sales"] = _daily_sales(captures, start=start, end=end, business_tz=business_tz)
    return data


def _daily_sales(captures, *, start, end, business_tz):
    amounts = {
        row["day"]: row["amount"]
        for row in captures.annotate(day=TruncDate("verified_at", tzinfo=business_tz))
        .values("day")
        .annotate(amount=Sum("captured_amount"))
        .order_by("day")
    }
    zero = Decimal("0.00")
    highest = max(amounts.values(), default=zero)
    points = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        amount = amounts.get(day, zero)
        percent = round(amount * 100 / highest) if highest else 0
        points.append({"day": day, "amount": amount, "percent": percent})
    return {"total": sum(amounts.values(), zero), "peak": highest, "points": points}
