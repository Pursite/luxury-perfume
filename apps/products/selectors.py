from uuid import UUID

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.products.filters import ProductFilter
from apps.products.models import Product, ProductImage


def get_public_products_queryset(*, request, view) -> QuerySet[Product]:
    """Return a filtered, searched, ordered, N+1-safe public catalogue query."""
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .prefetch_related("images")
    )
    filterset = ProductFilter(
        data=request.query_params,
        queryset=queryset,
        request=request,
    )
    if not filterset.is_valid():
        raise ValidationError(filterset.errors)

    queryset = filterset.qs
    queryset = SearchFilter().filter_queryset(request, queryset, view)
    if request.query_params.get("search"):
        queryset = queryset.distinct()
    return OrderingFilter().filter_queryset(request, queryset, view)


def get_product_by_uuid(
    *, product_uuid: UUID | str, include_inactive: bool = False
) -> Product:
    """Fetch a product by its public UUID, with relations needed for detail output."""
    queryset = Product.objects.select_related("category", "brand").prefetch_related(
        "images",
        "top_notes",
        "middle_notes",
        "base_notes",
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return get_object_or_404(queryset, uuid=product_uuid)


def get_product_detail(
    *, product_uuid: UUID | str, include_inactive: bool = False
) -> Product:
    """Semantic alias for the UUID-backed detail query."""
    return get_product_by_uuid(
        product_uuid=product_uuid,
        include_inactive=include_inactive,
    )


def get_product_image_by_id(*, image_id: int) -> ProductImage:
    """Fetch an image by its internal primary key for the admin delete endpoint."""
    return get_object_or_404(
        ProductImage.objects.select_related("product"),
        id=image_id,
    )
