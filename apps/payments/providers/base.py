from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

from apps.payments.exceptions import PaymentProviderProtocolError


class InitiationOutcome(StrEnum):
    READY = "ready"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class VerificationOutcome(StrEnum):
    VERIFIED = "verified"
    NOT_PAID = "not_paid"
    AMBIGUOUS = "ambiguous"


class RefundOutcome(StrEnum):
    REFUNDED = "refunded"
    ALREADY_REFUNDED = "already_refunded"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class PaymentInitiationResult:
    outcome: InitiationOutcome
    provider_session_id: str | None = None
    redirect_url: str | None = None
    diagnostic_code: str = ""


@dataclass(frozen=True)
class PaymentVerificationResult:
    outcome: VerificationOutcome
    provider_transaction_id: str | None = None
    provider_receipt_id: str | None = None
    captured_amount: Decimal | None = None
    captured_currency: str | None = None
    provider_paid_at: datetime | None = None
    diagnostic_code: str = ""


@dataclass(frozen=True)
class RefundResult:
    outcome: RefundOutcome
    provider_refund_id: str | None = None
    provider_receipt_id: str | None = None
    diagnostic_code: str = ""


class PaymentProvider(Protocol):
    def create_payment(self, *, payment_uuid, amount, currency, callback_url) -> PaymentInitiationResult: ...

    def verify_payment(self, *, provider_session_id, expected_amount, expected_currency) -> PaymentVerificationResult: ...

    def refund_payment(self, *, refund_uuid, provider_transaction_id, amount, currency) -> RefundResult: ...

    def lookup_payment(self, *, payment_uuid, expected_amount, expected_currency) -> PaymentInitiationResult: ...


def irt_to_rial(amount: Decimal) -> int:
    converted = Decimal(amount) * Decimal("10")
    if converted != converted.to_integral_value():
        raise PaymentProviderProtocolError("The IRT amount cannot be represented exactly in rial.")
    return int(converted)


def validate_redirect_url(url: str, *, allowed_hosts) -> str:
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise PaymentProviderProtocolError("The provider returned an unsafe redirect destination.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in set(allowed_hosts):
        raise PaymentProviderProtocolError("The provider returned an unsafe redirect destination.")
    if parsed.username or parsed.password:
        raise PaymentProviderProtocolError("The provider returned an unsafe redirect destination.")
    return url


def is_valid_provider_identifier(value, *, required=True) -> bool:
    if value is None:
        return not required
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 255
        and value == value.strip()
        and all(character.isprintable() for character in value)
    )
