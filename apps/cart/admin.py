from django.contrib import admin
from django.db.models import Count

from apps.cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    fields = ("product", "quantity", "created_at", "updated_at")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count", "created_at", "updated_at")
    search_fields = ("user__phone_number", "user__username", "user__email")
    readonly_fields = ("user", "created_at", "updated_at")
    inlines = (CartItemInline,)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(
                user__is_staff=False,
                user__is_superuser=False,
            )
        return queryset.select_related("user").annotate(_item_count=Count("items"))

    @admin.display(ordering="_item_count", description="Items")
    def item_count(self, cart):
        return cart._item_count

    @staticmethod
    def _has_object_access(request, cart):
        return request.user.is_superuser or not (
            cart and (cart.user.is_staff or cart.user.is_superuser)
        )

    def has_view_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_view_permission(
            request,
            obj,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
