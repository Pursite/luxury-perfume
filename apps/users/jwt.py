"""JWT extensions that bind tokens to the user's current password state."""

from secrets import compare_digest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import response as http_response
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.response import Response
from rest_framework import status

from apps.lib.throttle import TokenRefreshRateThrottle
from apps.users.permissions import CookieAuthOriginPermission


REFRESH_TOKEN_COOKIE_NAME = settings.REFRESH_TOKEN_COOKIE_NAME
REFRESH_TOKEN_COOKIE_PATH = settings.REFRESH_TOKEN_COOKIE_PATH


def mark_auth_response(response):
    """Prevent browsers and shared intermediaries caching auth responses."""
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def set_refresh_cookie(response, refresh_token: str):
    """Set a persistent cookie whose lifetime follows the token's exp claim."""
    token = RefreshToken(refresh_token, verify=False)
    expires_at = int(token["exp"])
    now = int(timezone.now().timestamp())
    max_age = max(0, expires_at - now)
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        expires=http_response.http_date(expires_at),
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )
    return response


def delete_refresh_cookie(response):
    """Delete using exactly the identity and scope used when creating it."""
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )
    return response


def token_response(*, payload: dict, tokens: dict[str, str], status_code: int):
    response_payload = dict(payload)
    response_payload["tokens"] = {"access": tokens["access"]}
    response = Response(response_payload, status=status_code)
    set_refresh_cookie(response, tokens["refresh"])
    return mark_auth_response(response)


class SensitiveAuthResponseMixin:
    """Apply no-store headers to every response from a sensitive auth view."""

    def finalize_response(self, request, response, *args, **kwargs):
        return mark_auth_response(super().finalize_response(request, response, *args, **kwargs))


def issue_tokens_for_user(user) -> dict[str, str]:
    """Issue the project-standard access and refresh token pair."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@transaction.atomic
def revoke_user_refresh_tokens(user):
    """Blacklist every unexpired refresh token while the user row is locked."""
    tokens = OutstandingToken.objects.select_for_update().filter(
        user=user,
        expires_at__gt=timezone.now(),
    )
    for token in tokens:
        BlacklistedToken.objects.get_or_create(token=token)


class PasswordRevocationTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject stale refresh tokens before rotation can mint a new access token."""

    @transaction.atomic
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        try:
            user = get_user_model().objects.select_for_update().get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except get_user_model().DoesNotExist as exc:
            raise TokenError("Token is invalid or expired.") from exc

        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise TokenError("Token is invalid or expired.")

        if api_settings.CHECK_REVOKE_TOKEN:
            token_password_hash = refresh.payload.get(api_settings.REVOKE_TOKEN_CLAIM, "")
            if not compare_digest(token_password_hash, get_md5_hash_password(user.password)):
                raise TokenError("Token is invalid or expired.")

        return super().validate(attrs)


class PasswordRevocationTokenRefreshView(SensitiveAuthResponseMixin, TokenRefreshView):
    serializer_class = PasswordRevocationTokenRefreshSerializer
    throttle_classes = (TokenRefreshRateThrottle,)
    permission_classes = (CookieAuthOriginPermission,)

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if not refresh_token:
            response = Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            delete_refresh_cookie(response)
            return response

        serializer = self.get_serializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            response = Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            delete_refresh_cookie(response)
            return response

        data = dict(serializer.validated_data)
        rotated_refresh = data.pop("refresh", None)
        response = Response(data, status=status.HTTP_200_OK)
        if rotated_refresh:
            set_refresh_cookie(response, rotated_refresh)
        return mark_auth_response(response)
