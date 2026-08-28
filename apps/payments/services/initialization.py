from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address
from uuid import UUID, uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.checkout import create_waiting_order
from apps.orders.services.transitions import expire_unpaid_order
from apps.payments.audit import emit_payment_event
from apps.payments.exceptions import (
    PaymentAttemptInProgressError,
    PaymentEligibilityError,
    PaymentInitiatorIPError,
    PaymentIdempotencyConflictError,
    PaymentNotFoundError,
    PaymentProviderProtocolError,
    PaymentProviderUnavailableError,
    ProviderProtocolError,
    ProviderSecurityError,
    ProviderTransportError,
)
from apps.payments.models import Payment
from apps.payments.providers.base import (
    InitiationOutcome,
    PaymentInitiationResult,
    is_valid_provider_identifier,
    validate_redirect_url,
)
from apps.payments.providers.registry import ProviderNotRegistered, get_provider


@dataclass(frozen=True)
class PaymentInitializationResult:
    payment: Payment
    order: Order
    redirect_url: str | None
    created: bool
    pending: bool
    retry_after_seconds: int = 5


def _sanitize_user_agent(value):
    return "".join(character for character in str(value or "") if character.isprintable())[:512]


def _canonical_initiator_ip(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise PaymentInitiatorIPError("A trusted client IP address is required.")
    try:
        return str(ip_address(value))
    except ValueError as exc:
        raise PaymentInitiatorIPError("A trusted client IP address is required.") from exc


def _adapter():
    try:
        return get_provider(settings.PAYMENT_PROVIDER)
    except ProviderNotRegistered as exc:
        raise PaymentProviderUnavailableError("Payment service is temporarily unavailable.") from exc


def _find_existing_payment(idempotency_key):
    return Payment.objects.select_related("order").filter(idempotency_key=idempotency_key).first()


def _replay(payment, *, user, address_uuid, order_uuid):
    if payment.order.user_id != user.pk:
        raise PaymentIdempotencyConflictError("The idempotency key conflicts with another payment.")
    if address_uuid is not None and payment.order.source_address_uuid != address_uuid:
        raise PaymentIdempotencyConflictError("The idempotency key conflicts with another payment.")
    if order_uuid is not None and payment.order.uuid != order_uuid:
        raise PaymentIdempotencyConflictError("The idempotency key conflicts with another payment.")
    redirect_url = None
    if (
        payment.provider_session_id
        and payment.status in (Payment.Status.REDIRECT_READY, Payment.Status.VERIFIED)
        and payment.order.status == Order.Status.WAITING_FOR_PAYMENT
        and timezone.now() < payment.order.reservation_expires_at
    ):
        adapter = _adapter()
        if not hasattr(adapter, "build_redirect_url"):
            raise PaymentProviderUnavailableError("Payment status is available but redirect recovery is unavailable.")
        redirect_url = validate_redirect_url(
            adapter.build_redirect_url(payment.provider_session_id),
            allowed_hosts=settings.PAYMENT_ALLOWED_REDIRECT_HOSTS,
        )
    return PaymentInitializationResult(
        payment=payment,
        order=payment.order,
        redirect_url=redirect_url,
        created=False,
        pending=payment.status in (Payment.Status.PENDING, Payment.Status.VERIFYING),
    )


def initialize_payment(
    *, user, idempotency_key, address_uuid=None, order_uuid=None,
    initiator_ip, initiator_user_agent, request_id,
):
    idempotency_key = UUID(str(idempotency_key))
    initiator_ip = _canonical_initiator_ip(initiator_ip)
    existing = _find_existing_payment(idempotency_key)
    if existing is not None:
        return _replay(existing, user=user, address_uuid=address_uuid, order_uuid=order_uuid)
    if (address_uuid is None) == (order_uuid is None):
        raise PaymentEligibilityError("Exactly one order source is required.")

    if address_uuid is not None:
        order, _created = create_waiting_order(
            user=user,
            address_id=address_uuid,
            idempotency_key=idempotency_key,
        )
    else:
        order = Order.objects.filter(user=user, uuid=order_uuid).first()
        if order is None:
            raise PaymentNotFoundError("Order not found.")

    token = uuid4()
    expired_order_id = None
    replay_payment = None
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            replay_payment = (
                Payment.objects.select_for_update()
                .select_related("order")
                .filter(idempotency_key=idempotency_key)
                .first()
            )
            if replay_payment is not None:
                pass
            else:
                if order.user_id != user.pk or order.status != Order.Status.WAITING_FOR_PAYMENT:
                    raise PaymentEligibilityError("The order is not eligible for payment.")
                now = timezone.now()
                if now >= order.reservation_expires_at:
                    expired_order_id = order.pk
                elif Payment.objects.filter(order=order, status__in=Payment.OPEN_STATUSES).exists():
                    raise PaymentAttemptInProgressError("A payment attempt is already in progress.")
                else:
                    payment = Payment.objects.create(
                        order=order,
                        provider=settings.PAYMENT_PROVIDER,
                        amount=order.total,
                        currency=settings.PAYMENT_CURRENCY,
                        idempotency_key=idempotency_key,
                        initiator_ip=initiator_ip,
                        initiator_user_agent=_sanitize_user_agent(initiator_user_agent),
                        initiator_request_id=request_id,
                        provider_requested_at=now,
                        next_reconciliation_at=now + timedelta(seconds=5),
                        operation_token=token,
                        operation_started_at=now,
                    )
    except IntegrityError as exc:
        existing = _find_existing_payment(idempotency_key)
        if existing is not None:
            return _replay(existing, user=user, address_uuid=address_uuid, order_uuid=order_uuid)
        raise PaymentAttemptInProgressError("A payment attempt is already in progress.") from exc
    if replay_payment is not None:
        return _replay(replay_payment, user=user, address_uuid=address_uuid, order_uuid=order_uuid)
    if expired_order_id is not None:
        expire_unpaid_order(order_id=expired_order_id)
        raise PaymentEligibilityError("The order reservation has expired.")

    try:
        adapter = _adapter()
    except PaymentProviderUnavailableError:
        _release_initiation_for_reconciliation(payment.pk, token, "provider_unavailable")
        emit_payment_event("payment_provider_error", payment=payment, outcome="provider_unavailable")
        raise
    callback_url = f"{settings.PAYMENT_PUBLIC_BASE_URL.rstrip('/')}/api/v1/payments/callback/{settings.PAYMENT_PROVIDER}/"
    try:
        result = adapter.create_payment(
            payment_uuid=payment.uuid,
            amount=payment.amount,
            currency=payment.currency,
            callback_url=callback_url,
        )
    except ProviderTransportError:
        emit_payment_event("payment_provider_error", payment=payment, outcome="transport")
        result = PaymentInitiationResult(outcome=InitiationOutcome.AMBIGUOUS, diagnostic_code="transport_error")
    except (ProviderProtocolError, ProviderSecurityError) as exc:
        _mark_initiation_review(payment.pk, token, "provider_protocol")
        emit_payment_event("payment_provider_error", payment=payment, outcome="provider_protocol")
        emit_payment_event("payment_manual_review_required", payment=payment, outcome="manual_review")
        raise PaymentProviderProtocolError("The payment provider returned an invalid response.") from exc

    if not isinstance(result, PaymentInitiationResult) or not isinstance(result.outcome, InitiationOutcome):
        _mark_initiation_review(payment.pk, token, "provider_protocol")
        emit_payment_event("payment_provider_error", payment=payment, outcome="provider_protocol")
        emit_payment_event("payment_manual_review_required", payment=payment, outcome="manual_review")
        raise PaymentProviderProtocolError("The payment provider returned an invalid response.")

    if result.outcome == InitiationOutcome.READY and not is_valid_provider_identifier(result.provider_session_id):
        _mark_initiation_review(payment.pk, token, "provider_protocol")
        emit_payment_event("payment_provider_error", payment=payment, outcome="provider_protocol")
        emit_payment_event("payment_manual_review_required", payment=payment, outcome="manual_review")
        raise PaymentProviderProtocolError("The payment provider returned an invalid response.")

    validated_redirect_url = None
    if result.outcome == InitiationOutcome.READY and result.redirect_url:
        try:
            validated_redirect_url = validate_redirect_url(
                result.redirect_url,
                allowed_hosts=settings.PAYMENT_ALLOWED_REDIRECT_HOSTS,
            )
        except PaymentProviderProtocolError:
            _mark_initiation_review(payment.pk, token, "unsafe_redirect")
            emit_payment_event("payment_provider_error", payment=payment, outcome="unsafe_redirect")
            emit_payment_event("payment_manual_review_required", payment=payment, outcome="manual_review")
            raise

    redirect_url = None
    expired_order_id = None
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.operation_token != token:
            return _replay(payment, user=user, address_uuid=address_uuid, order_uuid=order_uuid)
        payment.operation_token = None
        payment.operation_started_at = None
        fields = ["operation_token", "operation_started_at", "updated_at"]
        if result.outcome == InitiationOutcome.READY:
            if not result.provider_session_id or not result.redirect_url:
                _set_review(payment, "provider_protocol")
                fields += [
                    "status", "manual_review_at", "failure_code",
                    "next_reconciliation_at",
                ]
            else:
                redirect_url = validated_redirect_url
                payment.provider_session_id = result.provider_session_id
                payment.redirect_ready_at = timezone.now()
                payment.next_reconciliation_at = timezone.now() + timedelta(minutes=1)
                payment.status = Payment.Status.REDIRECT_READY
                fields += ["provider_session_id", "redirect_ready_at", "next_reconciliation_at", "status"]
                if order.status != Order.Status.WAITING_FOR_PAYMENT or timezone.now() >= order.reservation_expires_at:
                    redirect_url = None
                    expired_order_id = order.pk
        elif result.outcome == InitiationOutcome.REJECTED:
            payment.status = Payment.Status.FAILED
            payment.failed_at = timezone.now()
            payment.failure_code = (result.diagnostic_code or "initiation_rejected")[:64]
            fields += ["status", "failed_at", "failure_code"]
        else:
            payment.next_reconciliation_at = timezone.now() + timedelta(seconds=5)
            payment.failure_code = (result.diagnostic_code or "initiation_ambiguous")[:64]
            fields += ["next_reconciliation_at", "failure_code"]
        try:
            with transaction.atomic():
                payment.save(update_fields=fields)
        except IntegrityError:
            payment.provider_session_id = None
            payment.redirect_ready_at = None
            payment.next_reconciliation_at = None
            _set_review(payment, "provider_session_conflict")
            payment.save(update_fields=(
                "provider_session_id", "redirect_ready_at", "next_reconciliation_at",
                "status", "manual_review_at", "failure_code", "operation_token",
                "operation_started_at", "updated_at",
            ))
            redirect_url = None
    if expired_order_id is not None:
        expire_unpaid_order(order_id=expired_order_id)
    emit_payment_event(
        "payment_initialized",
        payment=payment,
        outcome=payment.status,
    )
    if result.outcome == InitiationOutcome.AMBIGUOUS:
        emit_payment_event(
            "payment_initiation_ambiguous",
            payment=payment,
            outcome="ambiguous",
        )
    elif payment.status == Payment.Status.MANUAL_REVIEW:
        emit_payment_event(
            "payment_manual_review_required",
            payment=payment,
            outcome="manual_review",
        )
    return PaymentInitializationResult(
        payment=payment,
        order=order,
        redirect_url=redirect_url,
        created=True,
        pending=result.outcome == InitiationOutcome.AMBIGUOUS or redirect_url is None,
    )


def _set_review(payment, code):
    payment.status = Payment.Status.MANUAL_REVIEW
    payment.manual_review_at = timezone.now()
    payment.failure_code = code
    payment.next_reconciliation_at = None
    payment.operation_token = None
    payment.operation_started_at = None


def _mark_initiation_review(payment_id, token, code):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.operation_token != token:
            return
        _set_review(payment, code)
        payment.save(update_fields=(
            "status", "manual_review_at", "failure_code",
            "next_reconciliation_at", "operation_token",
            "operation_started_at", "updated_at",
        ))


def _release_initiation_for_reconciliation(payment_id, token, code):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.operation_token != token:
            return
        payment.operation_token = None
        payment.operation_started_at = None
        payment.next_reconciliation_at = timezone.now() + timedelta(seconds=5)
        payment.failure_code = code
        payment.save(update_fields=(
            "operation_token", "operation_started_at", "next_reconciliation_at",
            "failure_code", "updated_at",
        ))
