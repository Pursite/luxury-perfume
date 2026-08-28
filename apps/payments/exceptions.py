class PaymentError(Exception):
    """Base class for customer-safe payment domain errors."""


class PaymentNotFoundError(PaymentError):
    pass


class PaymentEligibilityError(PaymentError):
    pass


class PaymentIdempotencyConflictError(PaymentError):
    pass


class PaymentAttemptInProgressError(PaymentError):
    pass


class PaymentProviderUnavailableError(PaymentError):
    pass


class PaymentProviderProtocolError(PaymentError):
    pass


class PaymentIntegrityError(PaymentError):
    pass


class RefundError(Exception):
    pass


class RefundNotEligibleError(RefundError):
    pass


class RefundProviderError(RefundError):
    pass


class ProviderTransportError(Exception):
    pass


class ProviderProtocolError(Exception):
    pass


class ProviderSecurityError(Exception):
    pass
