from django.urls import path

from apps.payments.views import PaymentCallbackAPIView, PaymentDetailAPIView, PaymentInitializeAPIView


app_name = "payments"

urlpatterns = [
    path("initialize/", PaymentInitializeAPIView.as_view(), name="initialize"),
    path("<uuid:payment_uuid>/", PaymentDetailAPIView.as_view(), name="detail"),
    path("callback/<slug:provider>/", PaymentCallbackAPIView.as_view(), name="callback"),
]
