from apps.lib.loggers import AppLogger
from apps.lib.tasks import CorrelatedTask
from celery import shared_task


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    base=CorrelatedTask,
)
def send_otp_sms_task(self, phone_number, otp_code):
    try:
        # TODO: Replace this placeholder with the production SMS provider client.
        # sending sms ...
        AppLogger.log_activity(msg="otp_sms.queued", status="INFO")
        return True

    except Exception:
        AppLogger.log_system_error(
            msg="otp_sms.delivery_failed",
            include_traceback=True,
        )
        raise
