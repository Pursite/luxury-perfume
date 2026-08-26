"""JWT extensions that bind tokens to the user's current password state."""

from secrets import compare_digest

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenRefreshView

from apps.lib.throttle import TokenRefreshRateThrottle


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


class PasswordRevocationTokenRefreshView(TokenRefreshView):
    serializer_class = PasswordRevocationTokenRefreshSerializer
    throttle_classes = (TokenRefreshRateThrottle,)
