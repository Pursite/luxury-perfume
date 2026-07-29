from apps.lib.loggers import AppLogger
from celery import shared_task


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_otp_sms_task(self, phone_number, otp_code):
    try:
        # TODO: Replace this placeholder with the production SMS provider client.
        # sending sms ...
        AppLogger.log_activity(msg=f"SMS queued successfully for {phone_number}", status="INFO")
        return True

    except Exception as e:
        AppLogger.log_system_error(f"Failed to send SMS to {phone_number}: {str(e)}", include_traceback=True)
        raise
