"""Shared exception primitives and the API error response contract."""

from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """Return DRF's safe default response with a stable error code field.

    Views and the browser data bridge can use ``error_code`` without relying
    on framework-specific exception serialization.  Exceptions that DRF does
    not handle deliberately remain unhandled so Django can log them.
    """
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        response.data.setdefault("error_code", getattr(exc, "default_code", "error"))
    return response
