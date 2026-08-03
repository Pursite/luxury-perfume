import pytest

from apps.users.tasks import send_otp_sms_task


def test_sms_task_reports_success_at_external_boundary(mocker):
    activity_log = mocker.patch("apps.users.tasks.AppLogger.log_activity")

    result = send_otp_sms_task.run("09123456789", "123456")

    assert result is True
    activity_log.assert_called_once()


def test_sms_task_reports_and_propagates_provider_failure(mocker):
    mocker.patch(
        "apps.users.tasks.AppLogger.log_activity",
        side_effect=RuntimeError("provider unavailable"),
    )
    error_log = mocker.patch("apps.users.tasks.AppLogger.log_system_error")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        send_otp_sms_task.run("09123456789", "123456")

    error_log.assert_called_once()

