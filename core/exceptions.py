"""Shared exception primitives and the API error response contract."""

import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Return stable machine-readable API errors and log where failures originate.

    Never log request bodies: they can contain credentials, strategy parameters,
    or other private user data. Log the API route, view, user identifier, status,
    and exception detail so operators can trace failures from production logs.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    view = context.get("view")
    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    path = getattr(request, "path", "<unknown>")
    method = getattr(request, "method", "<unknown>")
    view_name = view.__class__.__name__ if view is not None else "<unknown>"
    code = getattr(exc, "default_code", "error")

    if isinstance(response.data, dict):
        response.data.setdefault("error_code", code)
        response.data.setdefault("code", code)

    if response.status_code >= 500:
        logger.error(
            "API_REQUEST_FAILED status=%s method=%s path=%s view=%s user_id=%s code=%s detail=%s",
            response.status_code,
            method,
            path,
            view_name,
            user_id,
            code,
            response.data,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    elif response.status_code >= 400:
        logger.warning(
            "API_REQUEST_REJECTED status=%s method=%s path=%s view=%s user_id=%s code=%s detail=%s",
            response.status_code,
            method,
            path,
            view_name,
            user_id,
            code,
            response.data,
        )

    return response
