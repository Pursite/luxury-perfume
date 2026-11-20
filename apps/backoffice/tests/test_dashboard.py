from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.backoffice.permissions import BackofficeAccess
from apps.backoffice.selectors import get_dashboard_data, get_order_attention
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.tests.factories import OrderFactory, PaymentFactory
from apps.users.models import CustomUser
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db
DASHBOARD_URL = "admin:backoffice:dashboard"


def _verified_payment(order, verified_at, *, applied=True, currency="IRT", amount="100.00"):
    return PaymentFactory(
        order=order,
        status=Payment.Status.VERIFIED,
        verified_at=verified_at,
        captured_amount=amount,
        captured_currency=currency,
        applied_to_order_at=verified_at if applied else None,
        provider_session_id=str(uuid4()),
        provider_transaction_id=str(uuid4()),
        redirect_ready_at=verified_at,
    )


def test_dashboard_sales_use_verified_applied_irt_captures_at_store_midnight(staff_client):
    client = staff_client("payments.view_payment")
    zone = timezone.get_default_timezone()
    day = timezone.localdate(timezone=zone) - timedelta(days=2)
    first_midnight = datetime.combine(day, time.min, tzinfo=zone)
    next_midnight = first_midnight + timedelta(days=1)

    order = OrderFactory()
    _verified_payment(order, first_midnight, amount="100.05")
    _verified_payment(order, first_midnight, applied=False, amount="100.05")
    _verified_payment(OrderFactory(), next_midnight, amount="225.00")
    _verified_payment(OrderFactory(), first_midnight, applied=False, currency="USD", amount="900.00")
    _verified_payment(OrderFactory(), first_midnight - timedelta(microseconds=1))
    privileged_order = OrderFactory(source_address__user=UserFactory(is_staff=True))
    _verified_payment(privileged_order, first_midnight)
    PaymentFactory(order=OrderFactory())

    response = client.get(reverse(DASHBOARD_URL), {"start": day, "end": day})
    metrics = response.context["metrics"]
    assert response.status_code == 200
    assert tuple(metrics) == ("sales",)
    assert metrics["sales"] == {
        "total": Decimal("100.05"),
        "peak": Decimal("100.05"),
        "points": [{"day": day, "amount": Decimal("100.05"), "percent": 100}],
    }
    assert b"Recent orders" not in response.content
    assert b"New customers" not in response.content
    assert "attention" not in response.context
    assert b"Orders requiring attention" not in response.content


def test_dashboard_counts_orders_and_attention_without_privileged_owners(staff_client):
    client = staff_client("orders.view_order", "users.view_customuser")
    now = timezone.now()
    day = timezone.localdate(timezone=timezone.get_default_timezone())
    order = OrderFactory(status=Order.Status.PROCESSING, processing_at=now)
    shipped = OrderFactory(status=Order.Status.SHIPPED, processing_at=now, shipped_at=now)
    overdue = OrderFactory()
    Order.objects.filter(pk=overdue.pk).update(
        created_at=now - timedelta(days=1), reservation_expires_at=now - timedelta(hours=1),
    )
    waiting = OrderFactory()
    hidden = OrderFactory(source_address__user__is_superuser=True)
    new_customer = UserFactory()
    CustomUser.objects.filter(pk=new_customer.pk).update(created_at=now - timedelta(days=1))

    response = client.get(reverse(DASHBOARD_URL), {"start": day - timedelta(days=1), "end": day})
    metrics = response.context["metrics"]
    assert metrics["orders"] == {"total": 4}
    assert response.context["attention"] == {"total": 3, "to_ship": 1, "in_transit": 1, "overdue": 1}
    assert metrics["new_customers"] == 5
    assert [item.pk for item in metrics["recent_orders"]] == [waiting.pk, shipped.pk, order.pk, overdue.pk]
    assert str(hidden.uuid).encode() not in response.content
    assert b"Verified sales applied to orders" not in response.content


def test_live_attention_and_admin_links_include_old_unresolved_orders(staff_client, mocker):
    client = staff_client("orders.view_order")
    now = timezone.now()
    old_date = now - timedelta(days=120)
    processing = OrderFactory(status=Order.Status.PROCESSING, processing_at=old_date)
    shipped = OrderFactory(status=Order.Status.SHIPPED, processing_at=old_date, shipped_at=old_date)
    overdue = OrderFactory()
    Order.objects.filter(pk__in=(processing.pk, shipped.pk, overdue.pk)).update(
        created_at=old_date, reservation_expires_at=now,
    )
    pending = OrderFactory(reservation_expires_at=now + timedelta(hours=1))
    delivered = OrderFactory(
        status=Order.Status.DELIVERED, processing_at=old_date, shipped_at=old_date, delivered_at=old_date,
    )
    OrderFactory(status=Order.Status.CANCELLED, cancellation_reason=Order.CancellationReason.RESERVATION_EXPIRED, cancelled_at=now)
    OrderFactory(status=Order.Status.PROCESSING, processing_at=old_date, source_address__user__is_staff=True)
    mocker.patch("apps.orders.selectors.timezone.now", return_value=now)

    dashboard_url = reverse(DASHBOARD_URL)
    day = timezone.localdate(timezone=timezone.get_default_timezone())
    response = client.get(dashboard_url, {"start": day, "end": day})
    assert response.status_code == 200
    assert response.context["attention"] == {"total": 3, "to_ship": 1, "in_transit": 1, "overdue": 1}
    assert pending in response.context["metrics"]["recent_orders"]
    assert delivered in response.context["metrics"]["recent_orders"]
    assert not {processing, shipped, overdue}.intersection(response.context["metrics"]["recent_orders"])
    assert client.get(dashboard_url).context["attention"] == response.context["attention"]

    admin_url = reverse("admin:orders_order_changelist")
    for bucket, expected_order in (("to_ship", processing), ("in_transit", shipped), ("overdue", overdue)):
        url = f"{admin_url}?attention={bucket}"
        assert url.encode() in response.content
        filtered = client.get(url)
        assert filtered.status_code == 200
        assert list(filtered.context["cl"].result_list) == [expected_order]


def test_invalid_report_dates_leave_live_attention_available(staff_client):
    client = staff_client("orders.view_order")
    OrderFactory(status=Order.Status.PROCESSING, processing_at=timezone.now())
    response = client.get(reverse(DASHBOARD_URL), {"start": "invalid"})
    assert response.status_code == 400
    assert response.context["attention"]["to_ship"] == 1
    assert b"Open work across all order dates." in response.content
    assert b"Ready to ship" in response.content


@pytest.mark.parametrize("kind", ["required", "invalid", "reversed", "long", "future"])
def test_dashboard_rejects_invalid_date_ranges(staff_client, kind):
    client = staff_client("orders.view_order")
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    query = {
        "required": {"end": today},
        "invalid": {"start": "invalid", "end": today},
        "reversed": {"start": today, "end": today - timedelta(days=1)},
        "long": {"start": today - timedelta(days=90), "end": today},
        "future": {"start": today, "end": today + timedelta(days=1)},
    }[kind]
    response = client.get(reverse(DASHBOARD_URL), query)
    assert response.status_code == 400
    assert response.context["form"].errors


def test_dashboard_defaults_to_30_days_and_handles_empty_sales(staff_client):
    response = staff_client("payments.view_payment").get(reverse(DASHBOARD_URL))
    metrics = response.context["metrics"]
    assert metrics["sales"]["total"] == Decimal("0.00")
    assert len(metrics["sales"]["points"]) == 30
    assert b"No verified, order-applied sales in this period." in response.content


def test_date_presets_use_inclusive_store_calendar_days(staff_client):
    client = staff_client("payments.view_payment")
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    url = reverse(DASHBOARD_URL)
    presets = client.get(url).context["presets"]
    assert [entry["label"] for entry in presets] == ["Today", "Last 7 Days", "Last 30 Days"]
    assert [entry["active"] for entry in presets] == [False, False, True]
    for index, days in enumerate((1, 7, 30)):
        start = today - timedelta(days=days - 1)
        response = client.get(url, {"start": start, "end": today})
        assert len(response.context["metrics"]["sales"]["points"]) == days
        assert response.context["presets"][index]["active"]


def test_dashboard_reports_four_query_groups_and_limits_recent_orders(django_assert_num_queries):
    operator = UserFactory(is_staff=True)
    OrderFactory.create_batch(12)
    day = timezone.localdate(timezone=timezone.get_default_timezone())
    access = BackofficeAccess(orders=True, customers=True, sales=True, inventory=True)
    with django_assert_num_queries(4):
        metrics = get_dashboard_data(user=operator, access=access, start=day - timedelta(days=1), end=day)
        assert len(metrics["recent_orders"]) == 10
    assert metrics["orders"]["total"] == 12
    with django_assert_num_queries(1):
        assert get_order_attention(operator) == {"total": 0, "to_ship": 0, "in_transit": 0, "overdue": 0}
