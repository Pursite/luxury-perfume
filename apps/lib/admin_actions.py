from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.utils import model_ngettext
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _


def protected_delete_selected(
    *,
    modeladmin,
    request,
    queryset,
    action_name: str,
):
    """Run a two-step bulk delete through a ModelAdmin's protected service."""
    (
        deletable_objects,
        model_count,
        perms_needed,
        protected,
    ) = modeladmin.get_deleted_objects(queryset, request)
    blocking_perms = set() if request.user.is_superuser else perms_needed

    if request.POST.get("post"):
        if blocking_perms:
            raise PermissionDenied
        count = len(queryset)
        if count:
            with transaction.atomic():
                modeladmin.log_deletions(request, queryset)
                modeladmin.delete_queryset(request, queryset)
            modeladmin.message_user(
                request,
                _("Successfully deleted %(count)d %(items)s.")
                % {
                    "count": count,
                    "items": model_ngettext(modeladmin.opts, count),
                },
                messages.SUCCESS,
            )
        return None

    objects_name = model_ngettext(queryset)
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": _("Delete multiple objects"),
        "subtitle": None,
        "objects_name": str(objects_name),
        "deletable_objects": [deletable_objects],
        "model_count": dict(model_count).items(),
        "queryset": queryset,
        "perms_lacking": blocking_perms,
        "protected": protected,
        "opts": modeladmin.opts,
        "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        "action_name": action_name,
        "media": modeladmin.media,
    }
    request.current_app = modeladmin.admin_site.name
    return TemplateResponse(
        request,
        "admin/protected_delete_selected_confirmation.html",
        context,
    )
