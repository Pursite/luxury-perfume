import pytest

from apps.lib.sms.base import SmsSendOutcome, SmsSendResult
from apps.lib.sms.phone import mask_iranian_mobile, normalize_iranian_mobile


def test_normalize_iranian_mobile_accepts_only_canonical_ascii_local_numbers():
    assert normalize_iranian_mobile(" 09123456789 ") == "09123456789"
    assert normalize_iranian_mobile("+989123456789") is None
    assert normalize_iranian_mobile("۰۹۱۲۳۴۵۶۷۸۹") is None
    assert normalize_iranian_mobile("0912-345-6789") is None


def test_mask_iranian_mobile_retains_only_safe_edges():
    assert mask_iranian_mobile("09123456789") == "0912*****89"
    assert mask_iranian_mobile("invalid") == ""


def test_accepted_sms_result_requires_a_safe_provider_message_id():
    result = SmsSendResult(
        outcome=SmsSendOutcome.ACCEPTED,
        provider_message_id="message-123",
    )
    assert result.provider_message_id == "message-123"

    with pytest.raises(ValueError):
        SmsSendResult(outcome=SmsSendOutcome.ACCEPTED)

    with pytest.raises(ValueError):
        SmsSendResult(
            outcome=SmsSendOutcome.ACCEPTED,
            provider_message_id="unsafe\nidentifier",
        )
