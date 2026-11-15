import pytest

from apps.lib.sms.base import SmsSendOutcome, SmsSendResult
from apps.lib.sms import registry


@pytest.fixture
def operational_sms(settings, monkeypatch):
    class TestProvider:
        supports_idempotent_send = True

        def configuration_errors(self):
            return ()

        def send_sms(self, **kwargs):
            return SmsSendResult(
                SmsSendOutcome.ACCEPTED, provider_message_id="test-message"
            )

    monkeypatch.setitem(registry._providers, "users-test", TestProvider())
    settings.SMS_ENABLED = True
    settings.SMS_PROVIDER = "users-test"
