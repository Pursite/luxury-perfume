from django_filters import rest_framework as filters

from apps.products.models import Product


class ProductFilter(filters.FilterSet):
    """Filters available to the public product catalogue."""

    category = filters.UUIDFilter(field_name="category_id")
    brand = filters.UUIDFilter(field_name="brand_id")
    is_featured = filters.BooleanFilter()
    country_of_origin = filters.CharFilter(lookup_expr="iexact")
    vintage_year = filters.NumberFilter()
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    min_abv = filters.NumberFilter(field_name="abv", lookup_expr="gte")
    max_abv = filters.NumberFilter(field_name="abv", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = []

    def filter_in_stock(self, queryset, _name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)
