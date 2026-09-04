"""Origin validation for browser-facing API mutations.

Django CSRF protection remains enabled for normal HTML forms. API and data
endpoints do not require browser CSRF tokens; unsafe cookie-authenticated API
mutations must originate from an explicitly allowed AlgoBot origin. Bearer and
API-key clients can omit Origin because they do not authenticate with the
browser session cookie.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.http import JsonResponse


class APIOriginGuardMiddleware:
    """Protect API mutations with origin validation instead of CSRF tokens."""

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
        is_api = request.path.startswith(self.API_PREFIXES)
        if is_api:
            if request.method.upper() not in self.SAFE_METHODS and not self._is_authenticated_api_client(request):
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
                    return JsonResponse({"detail":"API request origin is not allowed.","code":"API_ORIGIN_FORBIDDEN"}, status=403)
            # API authentication and authorization remain authoritative. The
            # API-origin check above replaces the browser token requirement.
            request.csrf_processing_done = True
        return self.get_response(request)
