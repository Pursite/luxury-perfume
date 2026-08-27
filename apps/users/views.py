from django.conf import settings
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PhoneInputSerializer, VerifyOTPInputSerializer, UserPassLoginInputSerializer, \
    UserOutputSerializer, CompleteProfileInputSerializer, UserProfileUpdateInputSerializer, \
    PasswordResetVerifyInputSerializer, UserSignupInputSerializer, UserSignupOutputSerializer
from .services.signup_otp_service import SendOTPService
from .services.pass_reset_service import PasswordResetService
from .services.login_otp_service import LoginOtpService
from .services.profile_phone_service import ProfilePhoneVerificationService
from .jwt import SensitiveAuthResponseMixin, issue_tokens_for_user, token_response, delete_refresh_cookie
from .permissions import CookieAuthOriginPermission
from .selectors import UserSelector
from .services.signup_service import SignupIdentityConflict, create_user_service
from .services.user_auth_service import UserAuthService
from ..lib.loggers import AppLogger
from ..lib.throttle import (
    OTPPhoneNumberRateThrottle,
    OTPIPRateThrottle,
    OTPVerificationRateThrottle,
    OTPVerificationIPRateThrottle,
    PasswordLoginRateThrottle,
    SignupRateThrottle,
)


class UserSignupAPIView(SensitiveAuthResponseMixin, APIView):
    """Direct, anonymous username/password signup with a dedicated strict throttle."""

    permission_classes = (CookieAuthOriginPermission,)
    throttle_classes = (SignupRateThrottle,)

    def post(self, request):
        serializer = UserSignupInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = create_user_service(data=serializer.validated_data)
        except SignupIdentityConflict:
            return Response(
                {
                    "non_field_errors": [
                        UserSignupInputSerializer.default_error_message,
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        AppLogger.log_activity(msg="User registered with username/password", user=user)
        output_serializer = UserSignupOutputSerializer(user)
        return token_response(
            payload={"user": output_serializer.data},
            tokens=issue_tokens_for_user(user),
            status_code=status.HTTP_201_CREATED,
        )


class SendOTPCodeAPIView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (OTPPhoneNumberRateThrottle, OTPIPRateThrottle)

    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        result = SendOTPService.send_signup_otp(phone_number=phone_number)

        return Response(result, status=status.HTTP_200_OK)


class VerifyOTPAPIView(SensitiveAuthResponseMixin, APIView):
    permission_classes = (CookieAuthOriginPermission,)
    throttle_classes = (OTPVerificationRateThrottle, OTPVerificationIPRateThrottle)

    def post(self, request):
        serializer = VerifyOTPInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        submitted_otp = serializer.validated_data['otp']

        result = SendOTPService.verify_signup_otp(
            phone_number=phone_number,
            submitted_otp=submitted_otp
        )

        return token_response(
            payload={"message": result["message"]},
            tokens=result["tokens"],
            status_code=status.HTTP_201_CREATED,
        )


class LoginWithUserPassAPIView(SensitiveAuthResponseMixin, APIView):
    throttle_classes = (PasswordLoginRateThrottle,)
    permission_classes = (CookieAuthOriginPermission,)

    def post(self, request):
        serializer = UserPassLoginInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        result = LoginOtpService.login_with_username_password(
            username=username,
            password=password,
            client_ip=BaseThrottle().get_ident(request),
        )

        return token_response(
            payload={"message": result["message"]},
            tokens=result["tokens"],
            status_code=status.HTTP_200_OK,
        )


class SendOtpLoginAPIView(APIView):
    throttle_classes = (OTPPhoneNumberRateThrottle, OTPIPRateThrottle)
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        result = LoginOtpService.send_login_otp(phone_number=phone_number)

        return Response(result, status=status.HTTP_200_OK)


class LoginWithOTPCodeAPIView(SensitiveAuthResponseMixin, APIView):
    permission_classes = (CookieAuthOriginPermission,)
    throttle_classes = (OTPVerificationRateThrottle, OTPVerificationIPRateThrottle)

    def post(self, request):
        serializer = VerifyOTPInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        submitted_otp = serializer.validated_data['otp']

        result = LoginOtpService.verify_login_otp(
            phone_number=phone_number,
            submitted_otp=submitted_otp
        )

        return token_response(
            payload={"message": result["message"]},
            tokens=result["tokens"],
            status_code=status.HTTP_200_OK,
        )


class SendProfilePhoneOTPAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (OTPPhoneNumberRateThrottle, OTPIPRateThrottle)

    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ProfilePhoneVerificationService.send_phone_verification(
            user=request.user,
            phone_number=serializer.validated_data["phone_number"],
        )
        return Response(result, status=status.HTTP_200_OK)


class VerifyProfilePhoneOTPAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (OTPVerificationRateThrottle, OTPVerificationIPRateThrottle)

    def post(self, request):
        serializer = VerifyOTPInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = ProfilePhoneVerificationService.verify_phone_verification(
            user=request.user,
            phone_number=serializer.validated_data["phone_number"],
            submitted_otp=serializer.validated_data["otp"],
        )
        return Response(
            {
                "message": "phone number verified.",
                "data": UserOutputSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class CompleteProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CompleteProfileInputSerializer(
            data=request.data,
            context={'request': request}
        )

        serializer.is_valid(raise_exception=True)

        updated_user = UserAuthService.complete_user_profile(
            user=request.user,
            validated_data=serializer.validated_data
        )

        output_serializer = UserOutputSerializer(updated_user)

        return Response({
            "message": "your profile is successfully updated, and your account is registered",
            "data": output_serializer.data
        }, status=status.HTTP_200_OK)


class CurrentUserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = UserSelector.get_current_profile(user=request.user)
        return Response(
            {"data": UserOutputSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class UserProfileUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = UserProfileUpdateInputSerializer(
            data=request.data,
            context={'request': request},
            partial=True
        )

        serializer.is_valid(raise_exception=True)

        updated_user = UserAuthService.update_user_profile(
            user=request.user,
            validated_data=serializer.validated_data
        )

        output_serializer = UserOutputSerializer(updated_user)

        return Response({
            "message": "your profile is successfully updated.",
            "data": output_serializer.data
        }, status=status.HTTP_200_OK)


class LogoutAPIView(SensitiveAuthResponseMixin, APIView):
    authentication_classes = ()
    permission_classes = (CookieAuthOriginPermission,)

    def post(self, request):
        response = Response({"message": "successfully logged out."}, status=status.HTTP_200_OK)
        UserAuthService.logout_user(request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME))
        return delete_refresh_cookie(response)


class SendPasswordResetOtpAPIView(APIView):
    throttle_classes = (OTPPhoneNumberRateThrottle, OTPIPRateThrottle)
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        result = PasswordResetService.send_reset_otp(phone_number=phone_number)

        return Response(result, status=status.HTTP_200_OK)


class VerifyAndResetPasswordAPIView(SensitiveAuthResponseMixin, APIView):
    permission_classes = (CookieAuthOriginPermission,)
    throttle_classes = (OTPVerificationRateThrottle, OTPVerificationIPRateThrottle)

    def post(self, request):
        serializer = PasswordResetVerifyInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        result = PasswordResetService.verify_and_reset_password(
            phone_number=serializer.validated_data['phone_number'],
            submitted_otp=serializer.validated_data['otp'],
            new_password=serializer.validated_data['password']
        )

        return token_response(
            payload={"message": result["message"]},
            tokens=result["tokens"],
            status_code=status.HTTP_200_OK,
        )
