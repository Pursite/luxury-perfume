from django.contrib import admin
from .models import CustomUser, Address


class AddressInline(admin.TabularInline):
    model = Address
    extra = 1


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'username', 'first_name', 'last_name', 'is_active', 'is_staff',
                    'is_profile_complete')
    search_fields = ('phone_number', 'username', 'first_name', 'last_name', 'email')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    ordering = ('-created_at',)

    readonly_fields = ('created_at', 'updated_at')

    inlines = [AddressInline]

    fieldsets = (
        ('اطلاعات پایه', {
            'fields': ('phone_number', 'username', 'password')
        }),
        ('اطلاعات شخصی', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('دسترسی‌ها', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('تاریخ‌ها', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'postal_code')
    search_fields = ('user__phone_number', 'title', 'full_address')
