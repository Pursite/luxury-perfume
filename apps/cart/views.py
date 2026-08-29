from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.selectors import get_cart_items_for_user
from apps.cart.serializers import (
    CartItemAddInputSerializer,
    CartItemQuantityInputSerializer,
    CartOutputSerializer,
)
from apps.cart.services import (
    CartItemNotFoundError,
    CartProductUnavailableError,
    CartStockExceededError,
    add_cart_item_service,
    clear_cart_service,
    remove_cart_item_service,
    update_cart_item_quantity_service,
)


def _cart_response(*, request, response_status=status.HTTP_200_OK) -> Response:
    items = get_cart_items_for_user(user=request.user)
    serializer = CartOutputSerializer(items, context={"request": request})
    return Response(serializer.data, status=response_status)


def _raise_stock_validation_error(exc: CartStockExceededError) -> None:
    raise ValidationError(
        {"quantity": [_("Requested quantity exceeds available stock.")]}
    ) from exc


class CartAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        return _cart_response(request=request)

    def delete(self, request, *args, **kwargs):
        clear_cart_service(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemListAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = CartItemAddInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            _, created = add_cart_item_service(
                user=request.user,
                product_slug=serializer.validated_data["product_slug"],
                quantity=serializer.validated_data["quantity"],
            )
        except CartProductUnavailableError as exc:
            raise Http404 from exc
        except CartStockExceededError as exc:
            _raise_stock_validation_error(exc)

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return _cart_response(request=request, response_status=response_status)


class CartItemDetailAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, product_slug, *args, **kwargs):
        serializer = CartItemQuantityInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            update_cart_item_quantity_service(
                user=request.user,
                product_slug=product_slug,
                quantity=serializer.validated_data["quantity"],
            )
        except CartItemNotFoundError as exc:
            raise Http404 from exc
        except CartStockExceededError as exc:
            _raise_stock_validation_error(exc)
        return _cart_response(request=request)

    def delete(self, request, product_slug, *args, **kwargs):
        try:
            remove_cart_item_service(
                user=request.user,
                product_slug=product_slug,
            )
        except CartItemNotFoundError as exc:
            raise Http404 from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
