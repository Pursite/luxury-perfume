from django.contrib import admin
from .models import Category, Brand, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'is_primary', 'display_order')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'created_at')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'created_at')
    search_fields = ('name', 'country')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'uuid',
        'name',
        'category',
        'brand',
        'price',
        'discount_price',
        'stock',
        'abv',
        'volume_ml',
        'is_active',
        'is_featured'
    )
    list_filter = (
        'is_active',
        'is_featured',
        'category',
        'brand',
        'country_of_origin'
    )
    search_fields = ('name', 'sku', 'description', 'taste_notes')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('uuid',)
    inlines = [ProductImageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('uuid', 'name', 'slug', 'sku', 'category', 'brand', 'description')
        }),
        ('Pricing and Stock', {
            'fields': ('price', 'discount_price', 'stock')
        }),
        ('Alcohol Specifications', {
            'fields': (
                'abv',
                'volume_ml',
                'country_of_origin',
                'vintage_year',
                'ibu',
                'serving_temp',
                'taste_notes'
            )
        }),
        ('Status and Visibility', {
            'fields': ('is_active', 'is_featured')
        }),
    )