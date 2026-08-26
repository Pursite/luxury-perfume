from django.db.models import F, Prefetch, QuerySet, Window
from django.db.models.functions import RowNumber
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.products.filters import ProductFilter
from apps.products.models import Product, ProductFragranceNote, ProductImage


_PRODUCT_LIST_ONLY_FIELDS = (
    "uuid",
    "name",
    "slug",
    "sku",
    "price",
    "discount_price",
    "stock",
    "concentration",
    "target_audience",
    "fragrance_family",
    "introduction_year",
    "suitable_season",
    "suitable_usage_time",
    "volume_ml",
    "category_id",
    "brand_id",
    "is_featured",
    "created_at",
    "category__id",
    "category__name",
    "category__slug",
    "brand__id",
    "brand__name",
    "brand__slug",
    "brand__country",
)

_PRODUCT_LIST_IMAGE_ONLY_FIELDS = (
    "id",
    "product_id",
    "image",
    "thumbnail",
    "is_primary",
    "display_order",
)


def get_public_products_queryset(*, request, view) -> QuerySet[Product]:
    """Return a filtered, searched, ordered, N+1-safe public catalogue query."""
    list_image_queryset = (
        ProductImage.objects.only(*_PRODUCT_LIST_IMAGE_ONLY_FIELDS)
        .annotate(
            _list_image_rank=Window(
                expression=RowNumber(),
                partition_by=[F("product_id")],
                order_by=[F("is_primary").desc(), "display_order", "id"],
            )
        )
        .filter(_list_image_rank=1)
    )
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .only(*_PRODUCT_LIST_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "images",
                queryset=list_image_queryset,
                to_attr="_list_image",
            )
        )
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


def get_product_by_slug(
    *, product_slug: str, include_inactive: bool = False
) -> Product:
    """Fetch a product by its public slug, with relations needed for detail output."""
    queryset = Product.objects.select_related("category", "brand").prefetch_related(
        "images",
        Prefetch(
            "fragrance_note_links",
            queryset=ProductFragranceNote.objects.select_related(
                "fragrance_note"
            ).order_by("layer", "position", "id"),
            to_attr="_ordered_fragrance_note_links",
        ),
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return get_object_or_404(queryset, slug=product_slug)


def get_product_detail(
    *, product_slug: str, include_inactive: bool = False
) -> Product:
    """Semantic alias for the slug-backed detail query."""
    return get_product_by_slug(
        product_slug=product_slug,
        include_inactive=include_inactive,
    )


def get_product_image_by_id(*, image_id: int) -> ProductImage:
    """Fetch an image by its internal primary key for the admin delete endpoint."""
    return get_object_or_404(
        ProductImage.objects.select_related("product"),
        id=image_id,
    )
