"""Authentication helpers for browser-facing APIs."""
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.models import UserProfile


class BrowserSessionAuthentication(SessionAuthentication):
    """Authenticate browser sessions with Django/DRF CSRF protection."""


class BrokerGateJWTAuthentication(JWTAuthentication):
    """Reject JWTs that predate or bypass an enabled second-factor challenge."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        profile = UserProfile.objects.filter(user=user).only("two_factor_enabled").first()
        if profile and profile.two_factor_enabled and token.get("mfa_verified") is not True:
            raise AuthenticationFailed("Second-factor verification is required. Sign in again.")
        return user, token
