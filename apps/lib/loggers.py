import logging

activity_logger = logging.getLogger("activity")
security_logger = logging.getLogger("security")
system_logger = logging.getLogger("system")


class AppLogger:
    @staticmethod
    def log_activity(msg, user=None, status="INFO"):
        if user and user.is_authenticated:
            user_info = f"user_id={user.id}"
        else:
            user_info = "user=Anon"

        full_msg = f"{msg} | {user_info}"

        if status == "INFO":
            activity_logger.info(full_msg)
        elif status == "ERROR":
            activity_logger.error(full_msg)

    @staticmethod
    def log_security(msg, user=None, path=None):
        if user and user.is_authenticated:
            user_info = f"user_id={user.id}"
        else:
            user_info = "user=Anon"

        path_info = f"path={path if path else 'N/A'}"
        security_logger.warning(f"{msg} | {user_info} | {path_info}")

    @staticmethod
    def log_system_error(msg, include_traceback=False):
        system_logger.error(msg, exc_info=include_traceback)
