from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def csrf_token_view(request):
    """Bootstrap the browser CSRF cookie without exposing the token in JSON."""
    return JsonResponse({"ok": True})


def csrf_failure(request, reason=""):
    """Return machine-readable CSRF failures for API clients."""
    path = request.path or ""
    accepts_json = "application/json" in (request.headers.get("Accept") or "")
    if path.startswith(("/api/", "/data/")) or accepts_json:
        return JsonResponse(
            {
                "detail": "CSRF verification failed. Refresh the page and try again.",
                "code": "CSRF_FAILED",
            },
            status=403,
        )
    return django_csrf_failure(request, reason=reason)
