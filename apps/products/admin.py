from django.contrib import admin
from django.db.models import Case, IntegerField, Value, When

from apps.products.models import (
    Brand,
    Category,
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "is_primary", "display_order")


class ProductFragranceNoteInline(admin.TabularInline):
    model = ProductFragranceNote
    extra = 1
    fields = ("layer", "fragrance_note", "position")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                layer_order=Case(
                    When(layer=ProductFragranceNote.Layer.TOP, then=Value(0)),
                    When(layer=ProductFragranceNote.Layer.MIDDLE, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("layer_order", "position", "id")
        )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "created_at")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "created_at")
    search_fields = ("name", "country")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(FragranceNote)
class FragranceNoteAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "name",
        "category",
        "brand",
        "price",
        "discount_price",
        "stock",
        "concentration",
        "volume_ml",
        "is_active",
        "is_featured",
    )
    list_filter = (
        "is_active",
        "is_featured",
        "category",
        "brand",
        "concentration",
        "target_audience",
        "fragrance_family",
        "suitable_season",
        "suitable_usage_time",
        "country_of_origin",
    )
    search_fields = (
        "name",
        "sku",
        "description",
        "fragrance_note_links__fragrance_note__name",
    )
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uuid",)
    inlines = [ProductFragranceNoteInline, ProductImageInline]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "uuid",
                    "name",
                    "slug",
                    "sku",
                    "barcode",
                    "category",
                    "brand",
                    "description",
                ),
            },
        ),
        ("Pricing and Stock", {"fields": ("price", "discount_price", "stock")}),
        (
            "Fragrance Profile",
            {
                "fields": (
                    "concentration",
                    "target_audience",
                    "fragrance_family",
                    "introduction_year",
                    "suitable_season",
                    "suitable_usage_time",
                    "volume_ml",
                    "country_of_origin",
                ),
            },
        ),
        ("Status and Visibility", {"fields": ("is_active", "is_featured")}),
    )
