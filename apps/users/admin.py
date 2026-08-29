from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.users.forms import (
    CustomAdminPasswordChangeForm,
    CustomUserChangeForm,
    CustomUserCreationForm,
)
from apps.lib.admin_actions import protected_delete_selected
from apps.users.jwt import revoke_user_refresh_tokens
from apps.users.models import Address, CustomUser
from apps.users.services.user_service import (
    delete_addresses_service,
    delete_users_service,
    UserDeletionProtectedError,
)


def _is_privileged_user(user):
    return bool(user and (user.is_staff or user.is_superuser))


class AddressInline(admin.TabularInline):
    model = Address
    extra = 1

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "title":
            kwargs["help_text"] = _("For example: home or office.")
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    actions = ("delete_selected_users",)
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    change_password_form = CustomAdminPasswordChangeForm

    list_display = (
        "phone_number",
        "username",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_profile_complete",
    )
    search_fields = ("phone_number", "username", "first_name", "last_name", "email")
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("groups", "user_permissions")
    inlines = [AddressInline]

    add_fieldsets = (
        ("Identity", {"fields": ("phone_number", "username")}),
        (
            "Personal information",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Password",
            {"fields": ("usable_password", "password1", "password2")},
        ),
        ("Status", {"fields": ("is_active",)}),
    )
    fieldsets = (
        (
            "Identity",
            {"fields": ("phone_number", "username", "password")},
        ),
        (
            "Personal information",
            {"fields": ("first_name", "last_name", "email")},
        ),
        ("Status", {"fields": ("is_active",)}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )
    access_fieldset = (
        "Access and permissions",
        {
            "fields": ("is_staff", "is_superuser", "groups", "user_permissions"),
            "description": (
                "is_staff only permits admin-site login. Model access still "
                "requires group or direct permissions unless the user is a superuser."
            ),
        },
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = self.add_fieldsets if obj is None else self.fieldsets
        if request.user.is_superuser:
            return (*fieldsets, self.access_fieldset)
        return fieldsets

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(is_staff=False, is_superuser=False)
        return queryset.prefetch_related("addresses")

    @staticmethod
    def _is_privileged_user(obj):
        return _is_privileged_user(obj)

    def _has_object_access(self, request, obj):
        return request.user.is_superuser or not self._is_privileged_user(obj)

    def has_view_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_view_permission(
            request,
            obj,
        )

    def has_change_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_delete_permission(
            request,
            obj,
        )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            was_active = False
            if change:
                current_user = CustomUser.objects.select_for_update().get(pk=obj.pk)
                if not request.user.is_superuser:
                    if self._is_privileged_user(current_user):
                        raise PermissionDenied
                    obj.is_staff = current_user.is_staff
                    obj.is_superuser = current_user.is_superuser
                was_active = current_user.is_active
            elif not request.user.is_superuser:
                obj.is_staff = False
                obj.is_superuser = False

            super().save_model(request, obj, form, change)
            if change and was_active and not obj.is_active:
                revoke_user_refresh_tokens(obj)

    def user_change_password(self, request, id, form_url=""):
        if request.method != "POST":
            return super().user_change_password(request, id, form_url)

        try:
            user_id = self.model._meta.pk.to_python(unquote(id))
        except (ValidationError, ValueError) as exc:
            raise Http404 from exc

        with transaction.atomic():
            current_user = (
                CustomUser.objects.select_for_update().filter(pk=user_id).first()
            )
            if current_user is None or not self._has_object_access(
                request,
                current_user,
            ):
                raise Http404
            return super().user_change_password(request, id, form_url)

    def delete_model(self, request, obj):
        delete_users_service(
            user_ids=[obj.pk],
            allow_privileged=request.user.is_superuser,
        )

    def delete_queryset(self, request, queryset):
        delete_users_service(
            user_ids=queryset.values_list("pk", flat=True),
            allow_privileged=request.user.is_superuser,
        )

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except UserDeletionProtectedError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:users_customuser_changelist"))

    @admin.action(
        permissions=("delete",),
        description="Delete selected users",
    )
    def delete_selected_users(self, request, queryset):
        try:
            return protected_delete_selected(
                modeladmin=self,
                request=request,
                queryset=queryset,
                action_name="delete_selected_users",
            )
        except UserDeletionProtectedError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "postal_code")
    search_fields = ("user__phone_number", "title", "full_address")
    list_select_related = ("user",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "title":
            kwargs["help_text"] = _("For example: home or office.")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(
                user__is_staff=False,
                user__is_superuser=False,
            )
        return queryset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user" and not request.user.is_superuser:
            kwargs["queryset"] = CustomUser.objects.filter(
                is_staff=False,
                is_superuser=False,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @staticmethod
    def _has_object_access(request, obj):
        return request.user.is_superuser or not (
            obj and _is_privileged_user(obj.user)
        )

    def has_view_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_view_permission(
            request,
            obj,
        )

    def has_change_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return self._has_object_access(request, obj) and super().has_delete_permission(
            request,
            obj,
        )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            existing_owner_id = None
            if change:
                existing_owner_id = (
                    Address.objects.filter(pk=obj.pk)
                    .values_list("user_id", flat=True)
                    .first()
                )
                if existing_owner_id is None:
                    raise PermissionDenied

            owner_ids = {
                owner_id
                for owner_id in (existing_owner_id, obj.user_id)
                if owner_id is not None
            }
            locked_owners = {
                user.pk: user
                for user in CustomUser.objects.select_for_update()
                .filter(pk__in=owner_ids)
                .order_by("pk")
            }
            if obj.user_id not in locked_owners or (
                not request.user.is_superuser
                and any(
                    _is_privileged_user(user) for user in locked_owners.values()
                )
            ):
                raise PermissionDenied

            if change:
                current_address = (
                    Address.objects.select_for_update().filter(pk=obj.pk).first()
                )
                if (
                    current_address is None
                    or current_address.user_id != existing_owner_id
                ):
                    raise PermissionDenied

            return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        delete_addresses_service(
            address_ids=[obj.pk],
            allow_privileged=request.user.is_superuser,
        )

    def delete_queryset(self, request, queryset):
        delete_addresses_service(
            address_ids=queryset.values_list("pk", flat=True),
            allow_privileged=request.user.is_superuser,
        )


admin.site.unregister(Group)


@admin.register(Group)
class SuperuserGroupAdmin(GroupAdmin):
    @staticmethod
    def _is_allowed(request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self._is_allowed(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._is_allowed(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._is_allowed(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._is_allowed(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._is_allowed(request) and super().has_delete_permission(request, obj)
