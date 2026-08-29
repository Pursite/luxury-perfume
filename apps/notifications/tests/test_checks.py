from django.test import SimpleTestCase, override_settings

from apps.lib.sms.registry import register_provider
from apps.lib.tests.fakes import FakeSmsProvider
from apps.notifications.checks import check_sms_settings


class SmsSettingsChecksTests(SimpleTestCase):
    @override_settings(SMS_ENABLED=False)
    def test_disabled_sms_does_not_require_a_provider_or_owner_phone(self):
        assert check_sms_settings(None) == []

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="missing",
        SMS_CONNECT_TIMEOUT_SECONDS=3,
        SMS_READ_TIMEOUT_SECONDS=7,
        SMS_OPERATION_LEASE_SECONDS=30,
        SMS_MAX_ATTEMPTS=5,
        SMS_RETRY_BASE_SECONDS=5,
        SMS_RETRY_MAX_SECONDS=300,
        SMS_RECIPIENT_RETENTION_DAYS=180,
    )
    def test_enabled_sms_fails_closed_for_a_missing_provider_without_owner_phone_configuration(self):
        errors = check_sms_settings(None)

        assert {error.id for error in errors} == {"notifications.E001"}

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="check-fake",
        SMS_CONNECT_TIMEOUT_SECONDS=3,
        SMS_READ_TIMEOUT_SECONDS=7,
        SMS_OPERATION_LEASE_SECONDS=30,
        SMS_MAX_ATTEMPTS=5,
        SMS_RETRY_BASE_SECONDS=5,
        SMS_RETRY_MAX_SECONDS=300,
        SMS_RECIPIENT_RETENTION_DAYS=180,
    )
    def test_registered_valid_provider_passes_local_checks(self):
        register_provider("check-fake", FakeSmsProvider())

        assert check_sms_settings(None) == []
