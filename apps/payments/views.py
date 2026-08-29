from urllib.parse import urlencode
from uuid import UUID, uuid4

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.translation import gettext, gettext_lazy
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.lib.client_ip import get_trusted_client_ip
from apps.lib.log_context import get_request_id
from apps.lib.permissions import IsProfileComplete
from apps.orders.services.checkout import (
    ActiveCheckoutError,
    CheckoutAddressError,
    CheckoutError,
    CheckoutProfileIncompleteError,
    CheckoutUserInactiveError,
)
from apps.payments.exceptions import (
    PaymentAttemptInProgressError,
    PaymentEligibilityError,
    PaymentInitiatorIPError,
    PaymentIdempotencyConflictError,
    PaymentNotFoundError,
    PaymentProviderProtocolError,
    PaymentProviderUnavailableError,
)
from apps.payments.providers.registry import ProviderNotRegistered, get_provider
from apps.payments.selectors import get_owner_payment_queryset
from apps.payments.serializers import StrictInitializeInputSerializer, payment_payload
from apps.payments.services.initialization import initialize_payment
from apps.payments.services.verification import verify_payment
from apps.payments.throttles import PaymentCallbackRateThrottle, PaymentInitializeRateThrottle


class PaymentsUnavailable(APIException):
    status_code = 503
    default_detail = gettext_lazy("Payment service is temporarily unavailable.")
    default_code = "payments_unavailable"


def _ensure_enabled():
    if not settings.PAYMENTS_ENABLED:
        raise PaymentsUnavailable()


class PaymentInitializeAPIView(APIView):
    permission_classes = (IsAuthenticated, IsProfileComplete)
    throttle_classes = (PaymentInitializeRateThrottle,)

    def post(self, request):
        _ensure_enabled()
        serializer = StrictInitializeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_key = request.headers.get("Idempotency-Key")
        try:
            key = UUID(raw_key or "")
        except ValueError as exc:
            raise serializers.ValidationError({"Idempotency-Key": gettext("A valid UUID header is required.")}) from exc
        try:
            result = initialize_payment(
                user=request.user,
                idempotency_key=key,
                address_uuid=serializer.validated_data.get("address_uuid"),
                order_uuid=serializer.validated_data.get("order_uuid"),
                initiator_ip=get_trusted_client_ip(request),
                initiator_user_agent=request.headers.get("User-Agent", ""),
                request_id=get_request_id() or uuid4().hex,
            )
        except PaymentNotFoundError as exc:
            raise Http404 from exc
        except PaymentInitiatorIPError as exc:
            raise serializers.ValidationError({"detail": gettext("Unable to determine a trusted client address.")}) from exc
        except (PaymentIdempotencyConflictError, PaymentAttemptInProgressError, PaymentEligibilityError, ActiveCheckoutError) as exc:
            return Response({"code": "payment_conflict", "detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (PaymentProviderUnavailableError, PaymentProviderProtocolError) as exc:
            raise PaymentsUnavailable() from exc
        except (CheckoutProfileIncompleteError, CheckoutUserInactiveError) as exc:
            return Response({"code": "profile_not_ready", "detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (CheckoutAddressError, CheckoutError) as exc:
            raise serializers.ValidationError({"checkout": str(exc)}) from exc
        http_status = status.HTTP_202_ACCEPTED if result.pending else (status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)
        payload = payment_payload(result.payment, redirect_url=result.redirect_url, include_redirect=True)
        headers = None
        if result.pending:
            payload["retry_after_seconds"] = result.retry_after_seconds
            headers = {"Retry-After": str(result.retry_after_seconds)}
        return Response(payload, status=http_status, headers=headers)


class PaymentDetailAPIView(APIView):
    def get(self, request, payment_uuid):
        _ensure_enabled()
        payment = get_owner_payment_queryset(user=request.user).filter(uuid=payment_uuid).first()
        if payment is None:
            raise Http404
        return Response(payment_payload(payment), status=status.HTTP_200_OK)


class PaymentCallbackAPIView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (PaymentCallbackRateThrottle,)

    def get(self, request, provider):
        return self._handle(request, provider)

    def post(self, request, provider):
        return self._handle(request, provider)

    def _handle(self, request, provider):
        _ensure_enabled()
        try:
            adapter = get_provider(provider)
        except ProviderNotRegistered as exc:
            raise Http404 from exc
        if not hasattr(adapter, "parse_callback"):
            raise Http404
        try:
            provider_session_id, is_browser = adapter.parse_callback(
                method=request.method,
                query_params=request.query_params,
                data=request.data,
                headers=request.headers,
            )
        except Exception as exc:
            raise serializers.ValidationError({"callback": gettext("Invalid callback data.")}) from exc
        if not isinstance(provider_session_id, str) or not provider_session_id or len(provider_session_id) > 255:
            raise serializers.ValidationError({"callback": gettext("Invalid callback data.")})
        try:
            result = verify_payment(
                provider=provider,
                provider_session_id=provider_session_id,
                callback_ip=get_trusted_client_ip(request),
            )
        except PaymentNotFoundError as exc:
            raise Http404 from exc
        if is_browser:
            location = f"{settings.PAYMENT_FRONTEND_RESULT_URL}?{urlencode({'payment_uuid': str(result.payment.uuid)})}"
            return HttpResponse(status=303, headers={"Location": location})
        return HttpResponse(status=202 if result.pending else 204)
