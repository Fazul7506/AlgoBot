"""Authentication for the browser-facing API.

Cookie/session-authenticated browser requests remain CSRF protected through
DRF's SessionAuthentication boundary. Stateless Bearer/API-key clients do not
use this authenticator and therefore do not require a browser CSRF token.
"""

from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication


class BrowserSessionAuthentication(SessionAuthentication):
    """Session authentication with the normal DRF CSRF boundary."""

    def authenticate(self, request):
        user = getattr(request._request, "user", AnonymousUser())
        if not user or not user.is_authenticated:
            return None

        # Session-authenticated unsafe requests must carry a valid CSRF token.
        # JWT/API-key clients do not reach this authenticator.
        try:
            self.enforce_csrf(request)
        except exceptions.PermissionDenied:
            raise
        return (user, None)
