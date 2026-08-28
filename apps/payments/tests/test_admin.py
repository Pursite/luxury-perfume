import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from apps.payments.models import Payment, Refund
from apps.payments.tests.factories import PaymentFactory, RefundFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _request(user):
    request = RequestFactory().get("/admin/payments/payment/")
    request.user = user
    return request


def test_payment_admin_is_read_only_and_hides_privileged_owner_records():
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_payment", "change_payment")))
    ordinary = PaymentFactory()
    privileged = PaymentFactory(order__source_address__user=UserFactory(is_staff=True))
    model_admin = admin.site._registry[Payment]
    request = _request(delegated)

    queryset = model_admin.get_queryset(request)

    assert list(queryset.values_list("pk", flat=True)) == [ordinary.pk]
    assert model_admin.has_view_permission(request, ordinary)
    assert not model_admin.has_view_permission(request, privileged)
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request, ordinary) is False
    assert set(model_admin.get_readonly_fields(request, ordinary)) == {
        field.name for field in Payment._meta.fields
    }
    assert "provider_session_id" not in model_admin.get_fields(request, ordinary)
    assert "initiator_ip" not in model_admin.get_fields(request, ordinary)


def test_refund_admin_has_no_direct_financial_mutation_or_delete_controls():
    superuser = UserFactory(is_staff=True, is_superuser=True)
    refund = RefundFactory()
    model_admin = admin.site._registry[Refund]
    request = _request(superuser)

    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request, refund) is False
    assert set(model_admin.get_readonly_fields(request, refund)) == {
        field.name for field in Refund._meta.fields
    }
    assert "record_external_completion" in model_admin.get_actions(request)


def test_refund_admin_hides_financial_actions_from_delegated_staff():
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_refund", "change_refund")))
    model_admin = admin.site._registry[Refund]

    actions = model_admin.get_actions(_request(delegated))

    assert "retry_manual_review" not in actions
    assert "record_external_completion" not in actions


def test_refund_admin_hides_sensitive_fields_and_privileged_owner_records():
    delegated = UserFactory(is_staff=True)
    delegated.user_permissions.add(*Permission.objects.filter(codename__in=("view_refund", "change_refund")))
    ordinary = RefundFactory()
    privileged = RefundFactory(
        payment__order__source_address__user=UserFactory(is_staff=True)
    )
    model_admin = admin.site._registry[Refund]
    request = _request(delegated)

    queryset = model_admin.get_queryset(request)

    assert list(queryset.values_list("pk", flat=True)) == [ordinary.pk]
    assert model_admin.has_view_permission(request, ordinary)
    assert not model_admin.has_view_permission(request, privileged)
    assert "provider_refund_id" not in model_admin.get_fields(request, ordinary)
    assert "failure_code" not in model_admin.get_fields(request, ordinary)
    assert "completed_by" not in model_admin.get_fields(request, ordinary)
