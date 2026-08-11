from django.contrib import admin

from apps.products.models import Brand, Category, FragranceNote, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "is_primary", "display_order")


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
        "top_notes__name",
        "middle_notes__name",
        "base_notes__name",
    )
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uuid",)
    filter_horizontal = ("top_notes", "middle_notes", "base_notes")
    inlines = [ProductImageInline]

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
                    "top_notes",
                    "middle_notes",
                    "base_notes",
                    "volume_ml",
                    "country_of_origin",
                ),
            },
        ),
        ("Status and Visibility", {"fields": ("is_active", "is_featured")}),
    )
