"""Request outcome telemetry for the staff Mission Control activity stream."""
from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger("algobot.requests")
_IGNORED_PREFIXES = ("/static/", "/media/", "/health/", "/api/monitoring/mission-events/")
_IGNORED_PATHS = {"/favicon.ico"}
_SECRET = re.compile(r"(?i)(authorization|access[_-]?token|refresh[_-]?token|password|client[_-]?secret|api[_-]?key|secret)(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+")


def _response_detail(response):
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        value = data.get("user_message") or data.get("message") or data.get("detail") or data.get("error")
        if value is None and int(getattr(response, "status_code", 200) or 200) == 400:
            value = "; ".join(f"{key}: {str(item)[:180]}" for key, item in list(data.items())[:6] if key not in {"code", "error_code"})
    elif isinstance(data, str):
        value = data
    else:
        value = ""
    return _SECRET.sub(r"\1= [REDACTED]", str(value or ""))[:800]


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
            status_code = int(getattr(response, "status_code", 500) or 500)
            level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
            response_data = getattr(response, "data", None)
            response_data = response_data if isinstance(response_data, dict) else {}
            request_id = str(
                getattr(request, "request_id", "") or request.headers.get("X-Request-ID", "")
            )[:100]
            error_code = str(response_data.get("code") or response_data.get("error_code") or "")[:100]
            suggested_action = str(response_data.get("suggested_action") or "")[:500]
            category = "api_request"
            outcome = "failed" if status_code >= 400 else "completed"
            logger.log(
                level,
                "HTTP_REQUEST_COMPLETED status=%s method=%s path=%s duration_ms=%s request_id=%s detail=%s",
                status_code, getattr(request, "method", "UNKNOWN"), path, elapsed_ms, request_id, _response_detail(response),
                extra={
                    "category": category,
                    "status": outcome,
                    "operation_id": request_id or None,
                    "duration_ms": elapsed_ms,
                    "error_category": error_code or (f"http_{status_code}" if status_code >= 400 else None),
                    "resolution": suggested_action or None,
                },
            )
        return response
