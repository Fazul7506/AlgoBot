"""Compatibility middleware for browser/API separation.

AlgoBot's JSON APIs do not use Django CSRF tokens. Authentication, permissions,
origin/CORS policy, throttling, and broker authorization remain responsible for
API request protection. HTML/browser forms may continue to use Django CSRF
normally when this middleware delegates to the parent implementation.
"""

from django.middleware.csrf import CsrfViewMiddleware


class APIAwareCsrfViewMiddleware(CsrfViewMiddleware):
    """Do not require CSRF tokens on JSON API/data routes."""

    API_PREFIXES = ("/api/", "/data/")

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith(self.API_PREFIXES):
            request.csrf_processing_done = True
            return None
        return super().process_view(request, callback, callback_args, callback_kwargs)
