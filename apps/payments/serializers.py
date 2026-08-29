from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.orders.models import Order
from apps.payments.models import Payment, Refund


class StrictInitializeInputSerializer(serializers.Serializer):
    address_uuid = serializers.UUIDField(required=False)
    order_uuid = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: _("This field is not allowed.") for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if ("address_uuid" in attrs) == ("order_uuid" in attrs):
            raise serializers.ValidationError(_("Exactly one of address_uuid or order_uuid is required."))
        return attrs


class SafePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "uuid", "status", "amount", "currency", "provider_requested_at",
            "redirect_ready_at", "verified_at", "failed_at", "manual_review_at",
            "created_at", "updated_at",
        )


class SafeOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("uuid", "status", "reservation_expires_at")


class SafeRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ("uuid", "status", "reason", "amount", "currency", "created_at", "refunded_at", "manual_review_at")


def payment_payload(payment, *, redirect_url=None, include_redirect=False):
    refunds = getattr(payment, "safe_refunds", None)
    if refunds is None:
        refund = payment.refunds.order_by("id").first()
    else:
        refund = refunds[0] if refunds else None
    payload = {
        "payment": SafePaymentSerializer(payment).data,
        "order": SafeOrderSerializer(payment.order).data,
        "refund": SafeRefundSerializer(refund).data if refund else None,
    }
    if include_redirect:
        payload["redirect_url"] = redirect_url
    return payload
