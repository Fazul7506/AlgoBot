"""Best-effort persistence of application events for the Mission Control feed.

This handler deliberately stores only the rendered log message and logger name.
It never stores request bodies, headers, exception locals, or structured extras.
"""
from __future__ import annotations

import logging
import re

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)((?:access|refresh)?_?token|password|client_secret|api[_-]?key|secret)(\s*[:=]\s*)[^\s,;]+"),
)
_IGNORED_LOGGERS = ("django.db.backends", "apps.monitoring.logging_handlers", "urllib3", "websockets")


def _stream_for(logger_name: str) -> str:
    name = (logger_name or "").lower()
    if "security" in name or "auth" in name:
        return "security" if "security" in name else "authentication"
    if "broker" in name or "deriv" in name or "market" in name:
        return "broker"
    if "trading" in name or "execution" in name or "order" in name:
        return "trading"
    if "risk" in name:
        return "risk"
    if "strategy" in name:
        return "strategy"
    if "ai" in name or "model" in name:
        return "ai"
    if "celery" in name or "task" in name:
        return "celery"
    if "django" in name or "api" in name or "request" in name:
        return "api"
    return "application"


class MissionControlDatabaseHandler(logging.Handler):
    """Persist safe INFO+ events without allowing telemetry failures to break requests."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_IGNORED_LOGGERS):
            return
        try:
            from django.apps import apps
            if not apps.ready:
                return
            message = record.getMessage()
            for pattern in _SECRET_PATTERNS:
                message = pattern.sub(r"\1[REDACTED]", message)
            message = message[:4000]
            from .models import LogEntry
            LogEntry.objects.create(
                stream=_stream_for(record.name),
                level=record.levelname[:20],
                message=message,
                source=record.name[:160],
                context={},
            )
        except Exception:
            # Logging must never become a second source of application failure.
            return
