from celery import shared_task
from apps.lib.loggers import AppLogger


@shared_task
def send_otp_sms_task(phone_number, otp_code):
    try:

        msg = f"SMS Sent Successfully to {phone_number} with Code: {otp_code}"
        # sending sms ...
        AppLogger.log_activity(msg=msg, status="INFO")
        print(f"🔔 [Celery Task] OTP Code for Signup sent to {phone_number}: {otp_code}")
        return True

    except Exception as e:
        AppLogger.log_system_error(f"Failed to send SMS to {phone_number}: {str(e)}", include_traceback=True)
        return False