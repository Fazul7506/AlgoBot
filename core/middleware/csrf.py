"""CSRF boundary for browser-session and token-authenticated API requests.

Cookie-authenticated browser mutations remain CSRF protected. Bearer tokens are
explicit request credentials rather than ambient browser cookies, so API calls
that provide them do not need Django's cookie CSRF mechanism even when the
browser also has a session cookie. API views still validate the token and apply
their normal permission/account-context checks.
"""

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware


class APIAwareCsrfViewMiddleware(CsrfViewMiddleware):
    """Keep session-only API mutations protected while allowing Bearer APIs."""

    API_PREFIXES = ("/api/", "/data/")

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith(self.API_PREFIXES):
            session_cookie = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
            authorization = str(request.headers.get("Authorization", "")).strip()
            has_bearer_credentials = authorization.lower().startswith("bearer ")
            if not session_cookie or has_bearer_credentials:
                request.csrf_processing_done = True
                return None
        return super().process_view(request, callback, callback_args, callback_kwargs)
