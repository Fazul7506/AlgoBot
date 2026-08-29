"""Shared exception primitives and the API error response contract."""

from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """Return a stable machine-readable API error; AuditMiddleware owns UI messages."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        response.data.setdefault("error_code", getattr(exc, "default_code", "error"))
    return response
