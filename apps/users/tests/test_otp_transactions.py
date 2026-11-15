"""Service-level rollback coverage for every OTP-authorized database workflow."""

from functools import partial

import pytest
from django.db import DatabaseError

from apps.users.models import CustomUser, OTPChallenge
from apps.users.services.login_otp_service import LoginOtpService
from apps.users.services.pass_reset_service import PasswordResetService
from apps.users.services.profile_phone_service import ProfilePhoneVerificationService
from apps.users.services.signup_otp_service import SendOTPService
from apps.users.services.password_service import setup_guard, set_initial_password
from apps.users.tests.factories import UserFactory

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("operational_sms"),
]


@pytest.mark.parametrize("workflow", ["signup", "login", "reset", "phone", "setup"])
def test_database_failure_rolls_back_workflow_and_allows_same_otp_retry(
    workflow, mocker
):
    phone = "09123456789"
    user = None
    if workflow != "signup":
        user = UserFactory(phone_number=None if workflow == "phone" else phone)
        if workflow in ("phone", "setup"):
            user.set_unusable_password()
        else:
            user.set_password("OldStrongPass123!")
        user.save()
        original_password = user.password

    if workflow == "signup":
        guard = SendOTPService._guard(phone)
        invoke = partial(SendOTPService.verify_signup_otp, phone, "123456")
        target = "apps.users.services.signup_otp_service.issue_tokens_for_user"
    elif workflow == "login":
        guard = LoginOtpService._guard(phone)
        invoke = partial(LoginOtpService.verify_login_otp, phone, "123456")
        target = "apps.users.services.login_otp_service.issue_tokens_for_user"
    elif workflow == "reset":
        guard = PasswordResetService._guard(phone)
        invoke = partial(
            PasswordResetService.verify_and_reset_password,
            phone,
            "123456",
            "NewStrongPass123!",
        )
        target = "apps.users.services.pass_reset_service.issue_tokens_for_user"
    elif workflow == "setup":
        guard = setup_guard(user)
        invoke = partial(
            set_initial_password, user=user, otp="123456", password="NewStrongPass123!"
        )
        target = "apps.users.services.password_service.revoke_user_refresh_tokens"
    else:
        guard = ProfilePhoneVerificationService._guard(user, phone)
        invoke = partial(
            ProfilePhoneVerificationService.verify_phone_verification,
            user,
            phone,
            "123456",
        )
        target = "apps.users.models.CustomUser.save"

    guard.store_code("123456")
    failure = mocker.patch(target, side_effect=DatabaseError("simulated failure"))
    with pytest.raises(DatabaseError):
        invoke()
    assert OTPChallenge.objects.get(scope=guard.scope).redeemed_at is None
    if workflow == "signup":
        assert not CustomUser.objects.filter(phone_number=phone).exists()
    else:
        user.refresh_from_db()
        assert user.password == original_password
        if workflow == "phone":
            assert user.phone_number is None
    mocker.stop(failure)
    invoke()
    assert OTPChallenge.objects.get(scope=guard.scope).redeemed_at is not None
