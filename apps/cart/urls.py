from django.urls import path

from apps.cart.views import CartAPIView, CartItemDetailAPIView, CartItemListAPIView


app_name = "apps.cart"

urlpatterns = [
    path("", CartAPIView.as_view(), name="cart-detail"),
    path("items/", CartItemListAPIView.as_view(), name="cart-item-list"),
    path(
        "items/<slug:product_slug>/",
        CartItemDetailAPIView.as_view(),
        name="cart-item-detail",
    ),
]
