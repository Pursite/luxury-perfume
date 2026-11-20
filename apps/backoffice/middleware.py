from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class AdminLanguageMiddleware(MiddlewareMixin):
    """Use English for Admin requests while leaving other routes localized."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.resolver_match.app_names[:1] == ["admin"]:
            translation.activate("en")
            request.LANGUAGE_CODE = "en"
