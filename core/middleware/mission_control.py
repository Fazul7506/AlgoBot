"""Request outcome telemetry for the staff Mission Control activity stream."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("algobot.requests")
_IGNORED_PREFIXES = ("/static/", "/media/", "/health/", "/api/monitoring/mission-events/")
_IGNORED_PATHS = {"/favicon.ico"}


class MissionControlRequestLoggingMiddleware:
    """Record request outcome without logging query strings, headers, or bodies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request._mission_control_started = time.perf_counter()
        response = self.get_response(request)
        path = getattr(request, "path_info", "/")
        if path not in _IGNORED_PATHS and not path.startswith(_IGNORED_PREFIXES):
            elapsed_ms = round((time.perf_counter() - request._mission_control_started) * 1000, 2)
            user = getattr(request, "user", None)
            user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
            status_code = int(getattr(response, "status_code", 500) or 500)
            level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
            logger.log(
                level,
                "HTTP_REQUEST_COMPLETED status=%s method=%s path=%s duration_ms=%s user_id=%s",
                status_code, getattr(request, "method", "UNKNOWN"), path, elapsed_ms, user_id,
            )
        return response
