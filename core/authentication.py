"""Authentication helpers for browser-rendered AlgoBot pages and DRF APIs."""

from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication


class BrowserSessionOrJWTAuthentication(BaseAuthentication):
    """Accept the normal Django browser session, otherwise fall back to JWT.

    The dashboard is rendered by Django after login/OAuth, while API requests
    are consumed by JavaScript. Keeping the same browser session as the first
    authentication path prevents an expired/stale JWT from masking a valid
    Django session. JWT remains available for API clients and SPA-style flows.
    """

    def authenticate(self, request):
        session_result = SessionAuthentication().authenticate(request)
        if session_result is not None:
            return session_result
        return JWTAuthentication().authenticate(request)
