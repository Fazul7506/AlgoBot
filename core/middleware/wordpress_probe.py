"""Middleware helpers for low-value automated probes.

AlgoBot is not a WordPress installation. Internet scanners routinely probe
common WordPress paths; reject those signatures early so they never reach the
application URL resolver or business endpoints.
"""

from django.http import HttpResponseNotFound


class WordPressProbeMiddleware:
    """Short-circuit obvious WordPress scanner requests with a plain 404."""

    _PATH_MARKERS = (
        "/wp-admin/",
        "/wp-json/",
        "/wp-includes/",
        "/wp-content/",
        "/wp/v2/",
        "/wordpress/wp-",
        "/blog/wp-",
    )
    _ROOT_MARKERS = ("/wp/", "/wordpress/", "/blog/")

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def is_probe(cls, request):
        path = (request.path or "/").lower()
        query = (request.META.get("QUERY_STRING") or "").lower()
        method = request.method.upper()

        if any(marker in path for marker in cls._PATH_MARKERS):
            return True

        if any(path == marker or path.startswith(marker) for marker in cls._ROOT_MARKERS):
            return "rest_route=" in query or method != "GET"

        return False

    def __call__(self, request):
        if self.is_probe(request):
            return HttpResponseNotFound()
        return self.get_response(request)


class WordPressProbeLogFilter:
    """Hide known WordPress scanner 404s from normal application logs."""

    def filter(self, record):
        request = getattr(record, "request", None)
        path = str(getattr(request, "path", "") or "").lower()
        message = str(record.getMessage() or "").lower()
        markers = (
            "/wp-admin/",
            "/wp-json/",
            "/wp-includes/",
            "/wp-content/",
            "/wp/v2/",
            "/wordpress/wp-",
            "/blog/wp-",
        )
        return not any(marker in path or marker in message for marker in markers)
