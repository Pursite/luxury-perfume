from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    AdminUserCreationForm,
    UserChangeForm,
)

from apps.users.models import CustomUser
from apps.users.services.user_service import change_user_password_service


class _StaffSuperuserValidationMixin:
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_superuser") and not cleaned_data.get("is_staff"):
            self.add_error(
                "is_staff",
                "A superuser must also have admin-site access.",
            )
        return cleaned_data


class CustomUserCreationForm(
    _StaffSuperuserValidationMixin,
    AdminUserCreationForm,
):
    class Meta:
        model = CustomUser
        fields = (
            "phone_number",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


class CustomUserChangeForm(_StaffSuperuserValidationMixin, UserChangeForm):
    class Meta:
        model = CustomUser
        fields = "__all__"


class CustomAdminPasswordChangeForm(AdminPasswordChangeForm):
    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)

        raw_password = None
        if self.cleaned_data["set_usable_password"]:
            raw_password = self.cleaned_data["password1"]
        self.user = change_user_password_service(
            user=self.user,
            raw_password=raw_password,
        )
        return self.user
