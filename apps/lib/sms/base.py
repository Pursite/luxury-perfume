from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class SmsSendOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


def is_valid_provider_message_id(value: str | None, *, required: bool = False) -> bool:
    if value is None:
        return not required
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 255
        and value == value.strip()
        and value.isprintable()
    )


def is_valid_diagnostic_code(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 64
        and (not value or (value.isascii() and value.replace("_", "").replace("-", "").isalnum()))
    )


@dataclass(frozen=True)
class SmsSendResult:
    outcome: SmsSendOutcome
    provider_message_id: str | None = None
    diagnostic_code: str = ""

    def __post_init__(self):
        if not isinstance(self.outcome, SmsSendOutcome):
            raise ValueError("The SMS result outcome is invalid.")
        if not is_valid_provider_message_id(
            self.provider_message_id,
            required=self.outcome == SmsSendOutcome.ACCEPTED,
        ):
            raise ValueError("The provider message identity is invalid.")
        if self.outcome != SmsSendOutcome.ACCEPTED and self.provider_message_id is not None:
            raise ValueError("Only accepted SMS results may include a provider message identity.")
        if not is_valid_diagnostic_code(self.diagnostic_code):
            raise ValueError("The provider diagnostic code is invalid.")


class SmsProvider(Protocol):
    supports_idempotent_send: bool

    def send_sms(
        self,
        *,
        client_reference: UUID | str,
        recipient: str,
        message: str,
    ) -> SmsSendResult: ...

    def configuration_errors(self) -> tuple[str, ...]: ...


class SmsTransportError(Exception):
    """A transport failure known to occur before provider acceptance."""


class SmsProtocolError(Exception):
    """An invalid or untrusted provider response."""


class SmsConfigurationError(Exception):
    """A missing or invalid local provider configuration."""
