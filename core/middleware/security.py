"""Request-target validation applied before URL resolution."""

from django.http import HttpResponseBadRequest


class RejectMalformedPathMiddleware:
    """Reject duplicate-slash paths before a proxy can normalize them."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "//" in request.path:
            return HttpResponseBadRequest("Malformed URL path")
        return self.get_response(request)
