"""Authentication for browser-facing APIs.

Browser API requests are authenticated by the existing session/JWT boundary and,
for cookie sessions, protected by the API origin guard middleware. API clients
must not be required to bootstrap or submit a browser CSRF token.
"""

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import SessionAuthentication


class BrowserSessionAuthentication(SessionAuthentication):
    """Authenticate the browser session without DRF's CSRF token gate."""

    def authenticate(self, request):
        user = getattr(request._request, "user", AnonymousUser())
        if not user or not user.is_authenticated:
            return None
        return (user, None)
