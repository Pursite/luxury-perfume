from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.lib.paginations import CustomPagination
from apps.orders.selectors import get_user_order_detail_queryset, get_user_orders_queryset
from apps.orders.serializers import OrderDetailOutputSerializer, OrderListOutputSerializer


class OrderListAPIView(APIView):
    pagination_class = CustomPagination

    def get(self, request, *args, **kwargs):
        queryset = get_user_orders_queryset(user=request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = OrderListOutputSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderDetailAPIView(APIView):
    def get(self, request, order_uuid, *args, **kwargs):
        order = get_user_order_detail_queryset(user=request.user).filter(uuid=order_uuid).first()
        if order is None:
            raise Http404
        return Response(OrderDetailOutputSerializer(order).data, status=status.HTTP_200_OK)
