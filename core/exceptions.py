"""Shared exception primitives and the API error response contract."""

from django.contrib import messages
from rest_framework.views import exception_handler as drf_exception_handler


def _human_message(response, exc):
    """Extract only a short human-readable message; never expose JSON blobs."""
    data = getattr(response, "data", None)
    value = data.get("detail") if isinstance(data, dict) else None
    if not value and isinstance(data, dict):
        value = data.get("message") or data.get("error")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("message") or value.get("detail")
    text = str(value or getattr(exc, "detail", "Request could not be completed."))
    text = " ".join(text.split()).strip()
    if not text or text.startswith("{") or text.startswith("["):
        return "The requested operation could not be completed."
    return text[:500]


def custom_exception_handler(exc, context):
    """Keep API errors machine-readable while sending browser notifications through Django messages."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        response.data.setdefault("error_code", getattr(exc, "default_code", "error"))
        request = context.get("request")
        if request is not None and getattr(request, "user", None) is not None:
            level = messages.ERROR if response.status_code >= 500 else messages.WARNING
            messages.add_message(request, level, _human_message(response, exc), extra_tags="api-error")
    return response
