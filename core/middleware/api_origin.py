"""Origin validation for browser-facing API mutations.

Django's CSRF middleware remains available for normal HTML forms. API and data
endpoints do not require a browser CSRF token; unsafe browser mutations must
instead originate from an explicitly allowed AlgoBot origin. Bearer/API-key
clients are allowed to omit Origin because they do not authenticate with the
browser session cookie.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.http import JsonResponse


class APIOriginGuardMiddleware:
    """Protect cookie-authenticated API mutations without CSRF token plumbing."""

    API_PREFIXES = ("/api/", "/data/")
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _allowed_origins(request):
        configured = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or [])
        configured.update(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
        for value in (getattr(settings, "BASE_URL", ""), request.build_absolute_uri("/").rstrip("/")):
            if value:
                configured.add(value.rstrip("/"))
        return {str(origin).rstrip("/") for origin in configured if origin}

    @staticmethod
    def _is_authenticated_api_client(request):
        authorization = str(request.headers.get("Authorization") or "").strip().lower()
        api_key = str(request.headers.get("X-API-Key") or request.headers.get("Api-Key") or "").strip()
        return authorization.startswith("bearer ") or bool(api_key)

    def __call__(self, request):
        if request.path.startswith(self.API_PREFIXES) and request.method.upper() not in self.SAFE_METHODS:
            if not self._is_authenticated_api_client(request):
                origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
                referer = str(request.headers.get("Referer") or "").strip()
                referer_origin = ""
                if referer:
                    parsed = urlparse(referer)
                    if parsed.scheme and parsed.netloc:
                        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
                allowed = self._allowed_origins(request)
                if not origin:
                    origin = referer_origin
                if not origin or origin not in allowed:
                    return JsonResponse(
                        {
                            "detail": "API request origin is not allowed.",
                            "code": "API_ORIGIN_FORBIDDEN",
                        },
                        status=403,
                    )
        return self.get_response(request)
