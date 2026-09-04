"""Shared exception primitives and the API error response contract."""

from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """Return stable machine-readable API errors."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        code = getattr(exc, "default_code", "error")
        response.data.setdefault("error_code", code)
        response.data.setdefault("code", code)
    return response
