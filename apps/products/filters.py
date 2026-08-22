from django_filters import rest_framework as filters

from apps.products.models import Category, Product


class ProductFilter(filters.FilterSet):
    """Filters available to the public product catalogue."""

    category = filters.CharFilter(method="filter_category")
    brand = filters.UUIDFilter(field_name="brand_id")
    is_featured = filters.BooleanFilter()
    country_of_origin = filters.CharFilter(lookup_expr="iexact")
    concentration = filters.ChoiceFilter(choices=Product.Concentration.choices)
    target_audience = filters.ChoiceFilter(choices=Product.TargetAudience.choices)
    fragrance_family = filters.ChoiceFilter(choices=Product.FragranceFamily.choices)
    introduction_year = filters.NumberFilter()
    suitable_season = filters.ChoiceFilter(choices=Product.SuitableSeason.choices)
    suitable_usage_time = filters.ChoiceFilter(
        choices=Product.SuitableUsageTime.choices
    )
    note = filters.UUIDFilter(method="filter_note")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = []

    def filter_in_stock(self, queryset, _name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)

    def filter_note(self, queryset, _name, value):
        return queryset.filter(
            fragrance_note_links__fragrance_note_id=value
        ).distinct()

    def filter_category(self, queryset, _name, slug):
        root_id = (
            Category.objects.filter(slug=slug)
            .values_list("id", flat=True)
            .first()
        )
        if root_id is None:
            return queryset.none()

        category_ids = {root_id}
        pending_parent_ids = [root_id]
        while pending_parent_ids:
            child_ids = Category.objects.filter(
                parent_id__in=pending_parent_ids
            ).values_list("id", flat=True)
            pending_parent_ids = [
                child_id for child_id in child_ids if child_id not in category_ids
            ]
            category_ids.update(pending_parent_ids)

        return queryset.filter(category_id__in=category_ids)
