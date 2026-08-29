from celery import shared_task
from django.conf import settings

from apps.lib.loggers import AppLogger
from apps.lib.sms.base import (
    SmsConfigurationError,
    SmsProtocolError,
    SmsSendOutcome,
    SmsSendResult,
    SmsTransportError,
)
from apps.lib.sms.registry import ProviderNotRegistered, get_provider
from apps.lib.tasks import CorrelatedTask


class RedactedOtpTask(CorrelatedTask):
    """Prevent Celery worker/event argument representations from exposing OTPs."""

    abstract = True

    def apply_async(self, args=None, kwargs=None, **options):
        options.setdefault("argsrepr", "(<redacted-phone>, <redacted-otp>)")
        return super().apply_async(args=args, kwargs=kwargs, **options)


def _otp_message(otp_code):
    return f"کد تایید شما: {otp_code}"


@shared_task(
    bind=True,
    autoretry_for=(SmsTransportError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    base=RedactedOtpTask,
)
def send_otp_sms_task(self, phone_number, otp_code):
    """Send a Users-owned OTP without exposing values to logs or results."""
    if not getattr(settings, "SMS_ENABLED", False):
        AppLogger.log_activity(msg="otp_sms.disabled", status="INFO")
        return False
    try:
        provider = get_provider(settings.SMS_PROVIDER)
        if not callable(getattr(provider, "send_sms", None)):
            raise SmsConfigurationError
        result = provider.send_sms(
            client_reference=self.request.id or "otp-task",
            recipient=phone_number,
            message=_otp_message(otp_code),
        )
    except SmsTransportError:
        AppLogger.log_activity(msg="otp_sms.retryable_failure", status="INFO")
        raise
    except (ProviderNotRegistered, SmsConfigurationError, SmsProtocolError):
        AppLogger.log_activity(msg="otp_sms.delivery_failed", status="INFO")
        return False
    except Exception:
        AppLogger.log_activity(msg="otp_sms.delivery_failed", status="INFO")
        return False
    if not isinstance(result, SmsSendResult):
        AppLogger.log_activity(msg="otp_sms.delivery_failed", status="INFO")
        return False
    if result.outcome == SmsSendOutcome.ACCEPTED:
        AppLogger.log_activity(msg="otp_sms.sent", status="INFO")
        return True
    if result.outcome == SmsSendOutcome.AMBIGUOUS:
        AppLogger.log_activity(msg="otp_sms.ambiguous", status="INFO")
        if getattr(provider, "supports_idempotent_send", False):
            raise SmsTransportError
        return False
    AppLogger.log_activity(msg="otp_sms.delivery_failed", status="INFO")
    return False
