"""Authentication for the browser-facing API.

Cookie/session-authenticated browser requests remain CSRF protected through
DRF's SessionAuthentication boundary. Stateless Bearer/API-key clients do not
use this authenticator and therefore do not require a browser CSRF token.
"""

from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication


class CSRFAuthenticationFailed(exceptions.APIException):
    """Machine-readable 403 raised when a browser session fails CSRF."""

    status_code = 403
    default_detail = "CSRF verification failed. Refresh the page and try again."
    default_code = "CSRF_FAILED"


class BrowserSessionAuthentication(SessionAuthentication):
    """Session authentication with the normal DRF CSRF boundary."""

    def authenticate(self, request):
        user = getattr(request._request, "user", AnonymousUser())
        if not user or not user.is_authenticated:
            return None

        try:
            self.enforce_csrf(request)
        except exceptions.PermissionDenied as exc:
            raise CSRFAuthenticationFailed() from exc
        return (user, None)
