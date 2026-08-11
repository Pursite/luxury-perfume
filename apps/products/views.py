from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.lib.cache import RedisCacheService
from apps.lib.loggers import AppLogger
from apps.lib.paginations import CustomPagination
from apps.lib.permissions import IsAdmin
from apps.products.cache import (
    PRODUCT_DETAIL_CACHE_TTL,
    PRODUCT_LIST_CACHE_TTL,
    product_detail_cache_key,
    product_list_cache_key,
)
from apps.products.selectors import (
    get_product_by_uuid,
    get_product_detail,
    get_product_image_by_id,
    get_public_products_queryset,
)
from apps.products.serializers import (
    ProductDetailOutputSerializer,
    ProductImageOutputSerializer,
    ProductImageUploadInputSerializer,
    ProductListOutputSerializer,
    ProductWriteInputSerializer,
)
from apps.products.services import (
    create_product_image_service,
    create_product_service,
    delete_product_image_service,
    delete_product_service,
    update_product_service,
)


class ProductListCreateAPIView(APIView):
    """Public catalogue list and administrator-only product creation."""

    throttle_classes = (AnonRateThrottle, UserRateThrottle)
    pagination_class = CustomPagination
    search_fields = (
        "name",
        "sku",
        "description",
        "brand__name",
        "category__name",
        "fragrance_note_links__fragrance_note__name",
    )
    ordering_fields = (
        "price",
        "created_at",
        "introduction_year",
        "stock",
        "name",
        "volume_ml",
    )
    ordering = ("-created_at",)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [permissions.AllowAny()]

    def get(self, request, *args, **kwargs):
        cache_key = None
        if not request.user.is_authenticated:
            cache_key = product_list_cache_key(request)
            cached_data = RedisCacheService.get(cache_key)
            if cached_data is not None:
                return Response(cached_data, status=status.HTTP_200_OK)

        queryset = get_public_products_queryset(request=request, view=self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = ProductListOutputSerializer(
                page,
                many=True,
                context={"request": request},
            )
            response = paginator.get_paginated_response(serializer.data)
        else:
            serializer = ProductListOutputSerializer(
                queryset,
                many=True,
                context={"request": request},
            )
            response = Response(serializer.data, status=status.HTTP_200_OK)

        if cache_key is not None:
            RedisCacheService.set(
                cache_key,
                response.data,
                timeout=PRODUCT_LIST_CACHE_TTL,
            )
        return response

    def post(self, request, *args, **kwargs):
        serializer = ProductWriteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = create_product_service(validated_data=serializer.validated_data)
        AppLogger.log_activity(msg=f"Product created: {product.sku}", user=request.user)
        output = ProductDetailOutputSerializer(product, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProductDetailAPIView(APIView):
    """Public UUID detail and administrator-only UUID update/delete endpoints."""

    throttle_classes = (AnonRateThrottle, UserRateThrottle)

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsAdmin()]

    def get_object(self):
        include_inactive = bool(
            self.request.user.is_authenticated and self.request.user.is_staff
        )
        return get_product_detail(
            product_uuid=self.kwargs["product_uuid"],
            include_inactive=include_inactive,
        )

    def get(self, request, *args, **kwargs):
        cache_key = None
        if not request.user.is_authenticated:
            cache_key = product_detail_cache_key(
                product_uuid=self.kwargs["product_uuid"]
            )
            cached_data = RedisCacheService.get(cache_key)
            if cached_data is not None:
                return Response(cached_data, status=status.HTTP_200_OK)

        product = self.get_object()
        serializer = ProductDetailOutputSerializer(product, context={"request": request})
        response = Response(serializer.data, status=status.HTTP_200_OK)
        if cache_key is not None:
            RedisCacheService.set(
                cache_key,
                response.data,
                timeout=PRODUCT_DETAIL_CACHE_TTL,
            )
        return response

    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def _update(self, request, *, partial: bool):
        product = self.get_object()
        serializer = ProductWriteInputSerializer(
            product,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        product = update_product_service(
            product=product,
            validated_data=serializer.validated_data,
        )
        AppLogger.log_activity(msg=f"Product updated: {product.sku}", user=request.user)
        output = ProductDetailOutputSerializer(product, context={"request": request})
        return Response(output.data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        product = self.get_object()
        product_sku = product.sku
        delete_product_service(product=product)
        AppLogger.log_activity(msg=f"Product deleted: {product_sku}", user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductImageUploadAPIView(APIView):
    """Administrator-only multipart image upload addressed by the product UUID."""

    permission_classes = (IsAdmin,)
    throttle_classes = (AnonRateThrottle, UserRateThrottle)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, product_uuid, *args, **kwargs):
        product = get_product_by_uuid(product_uuid=product_uuid, include_inactive=True)
        serializer = ProductImageUploadInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_image = create_product_image_service(
            product=product,
            image_file=serializer.validated_data["image"],
            is_primary=serializer.validated_data["is_primary"],
            display_order=serializer.validated_data["display_order"],
        )
        AppLogger.log_activity(
            msg=f"Image uploaded for product: {product.sku}",
            user=request.user,
        )
        output = ProductImageOutputSerializer(
            product_image,
            context={"request": request},
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProductImageDeleteAPIView(APIView):
    """Administrator-only delete for an internally identified product image."""

    permission_classes = (IsAdmin,)
    throttle_classes = (AnonRateThrottle, UserRateThrottle)

    def delete(self, request, image_id, *args, **kwargs):
        product_image = get_product_image_by_id(image_id=image_id)
        product_sku = product_image.product.sku
        delete_product_image_service(product_image=product_image)
        AppLogger.log_activity(
            msg=f"Image deleted for product: {product_sku}",
            user=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
