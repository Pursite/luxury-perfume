from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PhoneInputSerializer, VerifyOTPInputSerializer, UserPassLoginInputSerializer, \
    UserOutputSerializer, CompleteProfileInputSerializer, UserProfileUpdateInputSerializer
from .services.signup_otp_service import SendOTPService
from .services.login_otp_service import LoginOtpService
from .services.user_auth_service import UserAuthService
from ..lib.throttles import OTPPhoneRateThrottle


class SendOTPCodeAPIView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = [OTPPhoneRateThrottle]

    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        result = SendOTPService.send_signup_otp(phone_number=phone_number)

        return Response(result, status=status.HTTP_200_OK)


class VerifyOTPAPIView(APIView):
    permission_classes = (AllowAny,)
    def post(self, request):
        serializer = VerifyOTPInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        submitted_otp = serializer.validated_data['otp']

        result = SendOTPService.verify_signup_otp(
            phone_number=phone_number,
            submitted_otp=submitted_otp
        )

        return Response(result, status=status.HTTP_201_CREATED)


class LoginWithUserPassAPIView(APIView):
    throttle_classes = [AnonRateThrottle]
    permission_classes = (AllowAny,)
    def post(self, request):
        serializer = UserPassLoginInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        result = LoginOtpService.login_with_username_password(username=username, password=password)

        return Response(result, status=status.HTTP_200_OK)


class SendOtpLoginAPIView(APIView):
    throttle_classes = [OTPPhoneRateThrottle]
    permission_classes = (AllowAny,)
    def post(self, request):
        serializer = PhoneInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        result = LoginOtpService.send_login_otp(phone_number=phone_number)

        return Response(result, status=status.HTTP_200_OK)


class LoginWithOTPCodeAPIView(APIView):
    permission_classes = (AllowAny,)
    def post(self, request):
        serializer = VerifyOTPInputSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        submitted_otp = serializer.validated_data['otp']

        result = LoginOtpService.verify_login_otp(
            phone_number=phone_number,
            submitted_otp=submitted_otp
        )

        return Response(result, status=status.HTTP_200_OK)


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
            "message": "your profile is successfully updated, and you`r account registered",
            "data": output_serializer.data
        }, status=status.HTTP_200_OK)


class UserProfileUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        try:
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
        except Exception as e:
            return Response({"error": "something happened back in servers"}, status=status.HTTP_400_BAD_REQUEST)

        output_serializer = UserOutputSerializer(updated_user)

        return Response({
            "message": "your profile is successfully updated.",
            "data": output_serializer.data
        }, status=status.HTTP_200_OK)
