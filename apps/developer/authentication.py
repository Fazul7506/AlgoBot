from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from .models import APIKey

class APIKeyAuthentication(BaseAuthentication):
    keyword = "ApiKey"

    def authenticate(self, request):
        key = request.headers.get("X-API-Key") or request.headers.get("Api-Key")
        secret = request.headers.get("X-API-Secret")
        if not key:
            auth = request.headers.get("Authorization", "")
            if auth.startswith(self.keyword + " "):
                key, _, secret = auth[len(self.keyword) + 1:].partition(":")
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
        valid_secret = check_password(secret, api_key.secret)
        if not valid_secret and api_key.previous_secret and api_key.previous_secret_expires_at:
            if api_key.previous_secret_expires_at > timezone.now():
                valid_secret = check_password(secret, api_key.previous_secret)
        if not valid_secret:
            raise AuthenticationFailed("Invalid API secret")
        return (api_key.user, api_key)
