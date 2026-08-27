from django import forms
from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Value, When
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.products.models import (
    Brand,
    Category,
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)
from apps.products.serializers import ProductImageUploadInputSerializer
from apps.products.services import (
    cleanup_product_image_original_after_rollback,
    create_product_image_in_transaction_service,
    delete_product_image_service,
    delete_product_service,
    delete_products_service,
    ProductDeletionProtectedError,
    ProductAdminUpdateValidationError,
    update_product_from_admin_service,
    update_product_image_service,
)


class ProductImageInlineForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ("image", "is_primary", "display_order")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uploaded_image = self.files.get(self.add_prefix("image"))
        if uploaded_image is not None:
            uploaded_image.declared_mime_type = uploaded_image.content_type

    def clean(self):
        cleaned_data = super().clean()
        self._validate_constraints = False
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image is None:
            return image
        if self.instance.pk:
            if "image" in self.changed_data:
                raise ValidationError(
                    "Delete this image and add a new one to replace its file."
                )
            return image

        serializer = ProductImageUploadInputSerializer(data={"image": image})
        if not serializer.is_valid():
            raise ValidationError([
                str(message) for message in serializer.errors.get("image", ())
            ])
        return serializer.validated_data["image"]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageInlineForm
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
    actions = ("delete_selected_products",)
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

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        request._created_product_images = []
        try:
            return super().changeform_view(
                request,
                object_id=object_id,
                form_url=form_url,
                extra_context=extra_context,
            )
        except ProductAdminUpdateValidationError as exc:
            for product_image in request._created_product_images:
                cleanup_product_image_original_after_rollback(product_image)
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(request.path)
        except Exception:
            for product_image in request._created_product_images:
                cleanup_product_image_original_after_rollback(product_image)
            raise
        finally:
            del request._created_product_images

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        changed_data = {
            field_name: form.cleaned_data[field_name]
            for field_name in form.changed_data
            if field_name in form.cleaned_data and field_name != "stock"
        }
        original_stock = form.initial.get("stock") if "stock" in form.changed_data else None
        submitted_stock = form.cleaned_data.get("stock") if "stock" in form.changed_data else None
        updated = update_product_from_admin_service(
            product_id=obj.pk,
            changed_data=changed_data,
            original_stock=original_stock,
            submitted_stock=submitted_stock,
        )
        obj.refresh_from_db()
        return updated

    def save_formset(self, request, form, formset, change):
        if formset.model is not ProductImage:
            return super().save_formset(request, form, formset, change)

        formset.save(commit=False)
        for product_image in formset.deleted_objects:
            delete_product_image_service(product_image=product_image)
        for product_image, _changed_fields in formset.changed_objects:
            update_product_image_service(
                product_image=product_image,
                is_primary=product_image.is_primary,
                display_order=product_image.display_order,
            )
        for product_image in formset.new_objects:
            created_image = create_product_image_in_transaction_service(
                product=formset.instance,
                image_file=product_image.image.file,
                is_primary=product_image.is_primary,
                display_order=product_image.display_order,
            )
            request._created_product_images.append(created_image)
        formset.save_m2m()

    def delete_model(self, request, obj):
        delete_product_service(product=obj)

    def delete_queryset(self, request, queryset):
        delete_products_service(
            product_ids=queryset.values_list("pk", flat=True),
        )

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ProductDeletionProtectedError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))

    @admin.action(description="Delete selected products")
    def delete_selected_products(self, request, queryset):
        try:
            return delete_selected(self, request, queryset)
        except ProductDeletionProtectedError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return super().get_readonly_fields(request, obj)
        return (*super().get_readonly_fields(request, obj), "slug")

    def get_prepopulated_fields(self, request, obj=None):
        if obj is not None:
            return {}
        return super().get_prepopulated_fields(request, obj)

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
