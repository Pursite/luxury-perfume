from django.urls import path
from . import views

app_name = 'apps.users'

urlpatterns = [
    path('signup/send-otp/', views.SendOTPCodeAPIView.as_view(), name='signup_send_otp'),
    path('signup/verify-otp/', views.VerifyOTPAPIView.as_view(), name='signup_verify_otp'),
    path('login/send-otp/', views.SendOtpLoginAPIView.as_view(), name='login_send_otp'),
    path('login/verify-otp/', views.LoginWithOTPCodeAPIView.as_view(), name='verify_login_otp'),
    path('login/userpass/', views.LoginWithUserPassAPIView.as_view(), name='login_password'),
    path('profile/complete/', views.CompleteProfileAPIView.as_view(), name='complete_profile'),
    path('profile/update/', views.UserProfileUpdateAPIView.as_view(), name='update_profile'),
]
