"""CSRF boundary for browser/session APIs and token-authenticated APIs.

JWT/API-token requests do not need Django's cookie CSRF mechanism. Requests that
carry a Django session cookie do: this includes function-based JSON endpoints
such as account settings that are authenticated by login_required.
"""

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware


class APIAwareCsrfViewMiddleware(CsrfViewMiddleware):
    """Skip CSRF only for API requests that are not using a browser session."""

    API_PREFIXES = ("/api/", "/data/")

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith(self.API_PREFIXES):
            session_cookie = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
            if not session_cookie:
                request.csrf_processing_done = True
                return None
        return super().process_view(request, callback, callback_args, callback_kwargs)
