import json
import logging
import re
import sys

from apps.lib.log_context import get_correlation_id, get_request_id
from apps.lib.cache import RedisCacheService
from apps.lib.logging import JsonFormatter, RequestContextFilter
from apps.lib.middleware import RequestIDMiddleware
from apps.users.tasks import send_otp_sms_task
from django.http import HttpResponse
from django.test import RequestFactory


def test_http_requests_receive_a_server_generated_request_id(api_client):
    response = api_client.get("/health/live")

    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


def test_request_identifier_is_scoped_to_the_request_and_not_client_controlled():
    observed_context = {}

    def get_response(request):
        observed_context["request_id"] = get_request_id()
        observed_context["correlation_id"] = get_correlation_id()
        return HttpResponse(status=204)

    request = RequestFactory().get("/health/live", HTTP_X_REQUEST_ID="a" * 32)
    response = RequestIDMiddleware(get_response)(request)

    assert response["X-Request-ID"] != "a" * 32
    assert observed_context == {
        "request_id": response["X-Request-ID"],
        "correlation_id": response["X-Request-ID"],
    }
    assert get_request_id() is None
    assert get_correlation_id() is None


def test_json_logging_redacts_sensitive_values_and_preserves_safe_context():
    record = logging.LogRecord(
        name="security",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="ignored",
        args=(),
        exc_info=None,
    )
    record.category = "security"
    record.event = "credential=do-not-log phone=09123456789"
    record.user_id = 42
    record.path = "/api/v1/users/token/"
    record.request_id = "a" * 32
    record.correlation_id = "a" * 32

    payload = json.loads(JsonFormatter().format(record))

    assert payload["category"] == "security"
    assert payload["user_id"] == 42
    assert payload["path"] == "/api/v1/users/token/"
    assert payload["request_id"] == "a" * 32
    assert payload["correlation_id"] == "a" * 32
    assert "do-not-log" not in payload["event"]
    assert "09123456789" not in payload["event"]


def test_django_error_records_do_not_forward_untrusted_error_messages():
    record = logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed request for 09123456789 with credential=do-not-log",
        args=(),
        exc_info=None,
    )

    RequestContextFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["category"] == "system"
    assert payload["event"] == "django.error"
    assert "09123456789" not in json.dumps(payload)
    assert "do-not-log" not in json.dumps(payload)


def test_structured_system_errors_record_exception_type_without_exception_text():
    try:
        raise RuntimeError("credential=do-not-log")
    except RuntimeError:
        record = logging.LogRecord(
            name="system",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="ignored",
            args=(),
            exc_info=sys.exc_info(),
        )
    record.category = "system"
    record.event = "cache.get.failed"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["exception_type"] == "RuntimeError"
    assert "do-not-log" not in json.dumps(payload)


def test_celery_task_uses_its_task_id_as_the_log_correlation_id(mocker):
    observed_correlation_ids = []
    mocker.patch(
        "apps.users.tasks.AppLogger.log_activity",
        side_effect=lambda **kwargs: observed_correlation_ids.append(
            get_correlation_id()
        ),
    )

    result = send_otp_sms_task.apply(args=("09123456789", "123456"))

    assert result.successful()
    assert observed_correlation_ids == [result.id]
    assert get_correlation_id() is None


def test_cache_failures_do_not_send_cache_keys_or_exception_text_to_logs(mocker):
    cache_get = mocker.patch(
        "apps.lib.cache.cache.get",
        side_effect=RuntimeError("credential=do-not-log"),
    )
    error_log = mocker.patch("apps.lib.cache.AppLogger.log_system_error")

    assert RedisCacheService.get("otp:09123456789") is None
    cache_get.assert_called_once_with("otp:09123456789")
    error_log.assert_called_once_with(msg="cache.get.failed")
