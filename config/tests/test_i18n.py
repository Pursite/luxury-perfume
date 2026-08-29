import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status

from apps.users.tests.factories import UserFactory


def test_backend_i18n_supports_only_english_and_persian_with_locale_between_session_and_common_middleware():
    """Removing LocaleMiddleware would make negotiated API errors stay in the default language."""
    assert settings.LANGUAGE_CODE == "en"
    assert settings.LANGUAGES == (("en", "English"), ("fa", "Persian"))
    assert settings.LOCALE_PATHS == (settings.BASE_DIR / "locale",)
    session_index = settings.MIDDLEWARE.index("django.contrib.sessions.middleware.SessionMiddleware")
    locale_index = settings.MIDDLEWARE.index("django.middleware.locale.LocaleMiddleware")
    common_index = settings.MIDDLEWARE.index("django.middleware.common.CommonMiddleware")
    assert session_index < locale_index < common_index


@pytest.mark.django_db
@pytest.mark.parametrize("username,password", (("unknown-user", "WrongPassword!"), ("known-user", "WrongPassword!")))
def test_persian_generic_password_failure_is_equal_for_unknown_and_wrong_password(api_client, username, password):
    """Separating localized failures by account state would reintroduce account enumeration."""
    user = UserFactory(username="known-user")
    user.set_password("SecurePass123!")
    user.save(update_fields=["password"])

    response = api_client.post(
        reverse("users:login_password"),
        {"username": username, "password": password},
        format="json",
        HTTP_ACCEPT_LANGUAGE="fa-IR,fa;q=0.9,en;q=0.8",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert set(response.data) == {"detail"}
    assert str(response.data["detail"]) == "نام کاربری یا رمز عبور نادرست است."


@pytest.mark.django_db
def test_unsupported_language_falls_back_to_existing_english_authentication_message(api_client):
    """Accepting an unsupported language must not change the stable English fallback semantics."""
    response = api_client.post(
        reverse("users:login_password"),
        {"username": "unknown-user", "password": "WrongPassword!"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="fr-CA,fr;q=0.9",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert str(response.data["detail"]) == "Username or password is incorrect."
