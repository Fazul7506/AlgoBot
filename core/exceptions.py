"""Shared exception primitives and trader-readable API error responses."""
from __future__ import annotations

import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("algobot.api")


def _flatten_errors(value, prefix=""):
    """Turn DRF's nested field-error structure into concise plain-language text."""
    if isinstance(value, dict):
        parts = []
        for key, child in value.items():
            label = f"{prefix} {key}".strip().replace("_", " ")
            parts.extend(_flatten_errors(child, label))
        return parts
    if isinstance(value, (list, tuple)):
        parts = []
        for child in value:
            parts.extend(_flatten_errors(child, prefix))
        return parts
    message = str(value).strip()
    if not message:
        return []
    return [f"{prefix}: {message}" if prefix else message]


def custom_exception_handler(exc, context):
    """Keep stable API codes, explain client mistakes, and log failure origins.

    Never log request bodies or headers; they may contain broker credentials,
    passwords, tokens, order details, or other private user data.
    """
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    view = context.get("view")
    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    path = getattr(request, "path", "<unknown>")
    method = getattr(request, "method", "<unknown>")
    view_name = view.__class__.__name__ if view is not None else "<unknown>"
    code = str(getattr(exc, "default_code", "error"))

    if response is None:
        logger.error(
            "API_REQUEST_UNHANDLED method=%s path=%s view=%s user_id=%s exception_type=%s detail=%s",
            method, path, view_name, user_id, type(exc).__name__, str(exc),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return None

    raw_data = response.data
    if isinstance(raw_data, dict):
        response.data.setdefault("error_code", code)
        response.data.setdefault("code", code)

    if response.status_code >= 500:
        # Keep server internals in logs, not in the response shown to a trader.
        safe_message = "AlgoBot could not complete this request. The issue has been recorded; please retry shortly."
        if isinstance(response.data, dict):
            response.data.setdefault("message", safe_message)
            response.data.setdefault("user_message", safe_message)
        logger.error(
            "API_REQUEST_FAILED status=%s method=%s path=%s view=%s user_id=%s code=%s exception_type=%s detail=%s",
            response.status_code, method, path, view_name, user_id, code,
            type(exc).__name__, raw_data,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    elif response.status_code >= 400:
        details = _flatten_errors(raw_data.get("detail", raw_data) if isinstance(raw_data, dict) else raw_data)
        readable = "; ".join(details[:8]) or "Please review the information and try again."
        if response.status_code == 400 and not (isinstance(raw_data, dict) and raw_data.get("detail")):
            readable = "Please check the information: " + readable
        if isinstance(response.data, dict):
            response.data.setdefault("message", readable)
            response.data.setdefault("user_message", readable)
        logger.warning(
            "API_REQUEST_REJECTED status=%s method=%s path=%s view=%s user_id=%s code=%s detail=%s",
            response.status_code, method, path, view_name, user_id, code, raw_data,
        )

    return response
