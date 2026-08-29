import pytest
from django.test import override_settings
from unittest.mock import patch

from apps.lib.sms.base import SmsSendOutcome, SmsSendResult, SmsTransportError
from apps.lib.sms.registry import register_provider
from apps.lib.tests.fakes import FakeSmsProvider
from apps.users.tasks import send_otp_sms_task


@override_settings(SMS_ENABLED=True, SMS_PROVIDER="otp-test")
def test_sms_task_sends_a_fixed_otp_message_with_the_task_reference(mocker):
    activity_log = mocker.patch("apps.users.tasks.AppLogger.log_activity")
    provider = FakeSmsProvider()
    register_provider("otp-test", provider)

    result = send_otp_sms_task.run("09123456789", "123456")

    assert result is True
    assert provider.calls[0]["recipient"] == "09123456789"
    assert provider.calls[0]["message"] == "کد تایید شما: 123456"
    activity_log.assert_called_once_with(msg="otp_sms.sent", status="INFO")


@override_settings(SMS_ENABLED=True, SMS_PROVIDER="otp-test")
def test_sms_task_retries_only_known_pre_acceptance_transport_failures(mocker):
    activity_log = mocker.patch("apps.users.tasks.AppLogger.log_activity")
    register_provider("otp-test", FakeSmsProvider(exception=SmsTransportError()))

    with pytest.raises(SmsTransportError):
        send_otp_sms_task.run("09123456789", "123456")

    activity_log.assert_called_once_with(msg="otp_sms.retryable_failure", status="INFO")


@override_settings(SMS_ENABLED=True, SMS_PROVIDER="otp-test")
def test_sms_task_stops_on_non_idempotent_ambiguity(mocker):
    activity_log = mocker.patch("apps.users.tasks.AppLogger.log_activity")
    provider = FakeSmsProvider(result=SmsSendResult(outcome=SmsSendOutcome.AMBIGUOUS))
    provider.supports_idempotent_send = False
    register_provider("otp-test", provider)

    assert send_otp_sms_task.run("09123456789", "123456") is False

    activity_log.assert_called_once_with(msg="otp_sms.ambiguous", status="INFO")


def test_otp_broker_metadata_redacts_task_arguments():
    with patch("apps.users.tasks.CorrelatedTask.apply_async") as apply_async:
        send_otp_sms_task.apply_async(args=("09123456789", "123456"))

    assert apply_async.call_args.kwargs["argsrepr"] == "(<redacted-phone>, <redacted-otp>)"
