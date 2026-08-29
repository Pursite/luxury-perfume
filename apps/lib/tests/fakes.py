from apps.lib.sms.base import SmsSendOutcome, SmsSendResult


class FakeSmsProvider:
    supports_idempotent_send = True

    def __init__(self, *, result=None, exception=None, configuration=()):
        self.result = result or SmsSendResult(
            outcome=SmsSendOutcome.ACCEPTED,
            provider_message_id="fake-message-1",
        )
        self.exception = exception
        self.configuration = configuration
        self.calls = []

    def send_sms(self, *, client_reference, recipient, message):
        self.calls.append(
            {
                "client_reference": client_reference,
                "recipient": recipient,
                "message": message,
            }
        )
        if self.exception:
            raise self.exception
        return self.result

    def configuration_errors(self):
        return self.configuration
