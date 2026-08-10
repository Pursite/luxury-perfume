import logging

from apps.lib.logging import sanitize_log_value

activity_logger = logging.getLogger("activity")
security_logger = logging.getLogger("security")
system_logger = logging.getLogger("system")


class AppLogger:
    @staticmethod
    def _user_id(user):
        if user and user.is_authenticated:
            return user.id
        return None

    @staticmethod
    def log_activity(msg, user=None, status="INFO", task_id=None):
        extra = {
            "category": "activity",
            "event": sanitize_log_value(msg),
            "user_id": AppLogger._user_id(user),
            "task_id": task_id,
        }
        if status == "INFO":
            activity_logger.info(msg, extra=extra)
        elif status == "ERROR":
            activity_logger.error(msg, extra=extra)

    @staticmethod
    def log_security(msg, user=None, path=None):
        security_logger.warning(
            msg,
            extra={
                "category": "security",
                "event": sanitize_log_value(msg),
                "user_id": AppLogger._user_id(user),
                "path": sanitize_log_value(path) if path else None,
            },
        )

    @staticmethod
    def log_system_error(msg, include_traceback=False):
        system_logger.error(
            msg,
            exc_info=include_traceback,
            extra={"category": "system", "event": sanitize_log_value(msg)},
        )
