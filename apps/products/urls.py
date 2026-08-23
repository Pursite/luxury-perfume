from django.urls import path

from apps.products.views import (
    ProductDetailAPIView,
    ProductImageDeleteAPIView,
    ProductImageUploadAPIView,
    ProductListCreateAPIView,
)

app_name = "apps.products"

urlpatterns = [
    path("", ProductListCreateAPIView.as_view(), name="product-list"),
    path("<slug:product_slug>/", ProductDetailAPIView.as_view(), name="product-detail"),
    path(
        "<slug:product_slug>/images/upload/",
        ProductImageUploadAPIView.as_view(),
        name="product-image-upload",
    ),
    path(
        "images/<int:image_id>/",
        ProductImageDeleteAPIView.as_view(),
        name="product-image-delete",
    ),
]
