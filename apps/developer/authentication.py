from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.hashers import check_password
from django.utils import timezone

from .models import APIKey


class APIKeyAuthentication(BaseAuthentication):
    """Authenticate first-party API clients without breaking browser sessions.

    Supported forms:
      X-API-Key + X-API-Secret
      Api-Key + Api-Secret
      Authorization: ApiKey <key>:<secret>
      Authorization: Bearer <key>:<secret>

    Returning ``None`` when no API credential is present is intentional: DRF
    can then continue to SessionAuthentication for the logged-in Developer UI.
    """

    keywords = ("ApiKey", "Bearer")

    def authenticate(self, request):
        key = request.headers.get("X-API-Key") or request.headers.get("Api-Key")
        secret = request.headers.get("X-API-Secret") or request.headers.get("Api-Secret")

        authorization = request.headers.get("Authorization", "").strip()
        if not key and authorization:
            scheme, _, credentials = authorization.partition(" ")
            if scheme in self.keywords:
                key, separator, parsed_secret = credentials.partition(":")
                secret = parsed_secret if separator else secret

        if not key:
            return None
        if not secret:
            raise AuthenticationFailed("API secret is required")

        try:
            api_key = APIKey.objects.select_related("user").get(key=key)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key")

        if not api_key.is_active():
            raise AuthenticationFailed("API key is inactive, revoked, or expired")

        now = timezone.now()
        valid_secret = check_password(secret, api_key.secret)
        if (
            not valid_secret
            and api_key.previous_secret
            and api_key.previous_secret_expires_at
            and api_key.previous_secret_expires_at > now
        ):
            valid_secret = check_password(secret, api_key.previous_secret)

        if not valid_secret:
            raise AuthenticationFailed("Invalid API secret")

        APIKey.objects.filter(pk=api_key.pk).update(last_used=now)
        return (api_key.user, api_key)

    def authenticate_header(self, request):
        return "ApiKey"
