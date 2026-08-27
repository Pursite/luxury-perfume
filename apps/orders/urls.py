from django.urls import path

from apps.orders.views import OrderDetailAPIView, OrderListAPIView


app_name = "orders"

urlpatterns = [
    path("", OrderListAPIView.as_view(), name="order-list"),
    path("<uuid:order_uuid>/", OrderDetailAPIView.as_view(), name="order-detail"),
]
