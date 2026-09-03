"""Authentication for the browser-facing API.

The web application and API are sibling subdomains and intentionally share the
Django login session. DRF's stock SessionAuthentication additionally requires a
CSRF token on every unsafe request, which is brittle when the API is hosted on
api.algobot.dpdns.org. This authenticator keeps session authentication but uses
strict Origin/Referer validation for unsafe browser requests instead of a CSRF
token. JWT clients continue to work through the normal JWT authenticator.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication


class BrowserSessionAuthentication(SessionAuthentication):
    """Session authentication with origin-bound unsafe-request protection."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    @staticmethod
    def _normalise_origin(value):
        value = str(value or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")

    def _allowed_origins(self, request):
        allowed = set()
        for source in (
            getattr(settings, "CORS_ALLOWED_ORIGINS", []),
            getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
        ):
            for value in source or []:
                origin = self._normalise_origin(value)
                if origin:
                    allowed.add(origin)

        try:
            allowed.add(self._normalise_origin(request.build_absolute_uri("/") ))
        except Exception:
            pass
        return allowed

    def _validate_origin(self, request):
        if request.method.upper() in self.SAFE_METHODS:
            return

        headers = request.headers
        origin = self._normalise_origin(headers.get("Origin"))
        referer = self._normalise_origin(headers.get("Referer"))
        fetch_site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
        allowed = self._allowed_origins(request)

        # Browsers normally send Origin for fetch/XHR POSTs. Referer is the
        # standards-compatible fallback for clients that omit Origin.
        supplied = origin or referer
        if supplied and supplied in allowed:
            return
        if not supplied and fetch_site in {"same-origin", "same-site"}:
            return

        raise exceptions.AuthenticationFailed(
            "Unsafe API request origin is not trusted."
        )

    def authenticate(self, request):
        user = getattr(request._request, "user", AnonymousUser())
        if not user or not user.is_authenticated:
            return None
        self._validate_origin(request)
        return (user, None)
