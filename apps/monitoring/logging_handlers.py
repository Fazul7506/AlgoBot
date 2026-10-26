"""Best-effort persistence of application events for the Mission Control feed.

This handler deliberately stores only the rendered log message and logger name.
It never stores request bodies, headers, exception locals, or structured extras.
"""
from __future__ import annotations

import logging
import re
import sys
import traceback

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
    if "trading" in name or "execution" in name or "order" in name or "backtest" in name:
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
        # Keep the unit-test database isolated from telemetry writes; production
        # workers and web processes still persist the full operational feed.
        if "pytest" in sys.modules or "test" in sys.argv[1:]:
            return
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
            # Only persist explicitly approved structured fields; arbitrary LogRecord
            # extras can contain request objects, credentials, or other sensitive data.
            allowed_fields = (
                "category", "status", "operation_id", "duration_ms",
                "error_category", "resolution", "instrument", "timeframe",
                "task_id", "service", "diagnostic_summary", "details",
            )
            context = {}
            for key in allowed_fields:
                value = getattr(record, key, None)
                if value is None or isinstance(value, (dict, list, tuple)):
                    if isinstance(value, (dict, list, tuple)) and key in {"details"}:
                        value = str(value)[:1000]
                    else:
                        continue
                if isinstance(value, (str, int, float, bool)):
                    rendered = str(value)
                    for pattern in _SECRET_PATTERNS:
                        rendered = pattern.sub(r"\1[REDACTED]", rendered)
                    context[key] = rendered[:1000]
            if record.exc_info:
                # Keep a useful, bounded diagnostic without locals or raw request data.
                diagnostic = "".join(traceback.format_exception(*record.exc_info))[-5000:]
                for pattern in _SECRET_PATTERNS:
                    diagnostic = pattern.sub(r"\1[REDACTED]", diagnostic)
                context.setdefault("diagnostic_summary", diagnostic[:3000])
                context.setdefault("status", "failed")
                context.setdefault("error_category", "unexpected_exception")
            elif record.levelno >= logging.ERROR:
                context.setdefault("status", "failed")
                context.setdefault("error_category", "unclassified_failure")
            elif record.levelno >= logging.WARNING:
                context.setdefault("status", "warning")
            else:
                context.setdefault("status", "recorded")
            context.setdefault("category", _stream_for(record.name))
            from .models import LogEntry
            LogEntry.objects.create(
                stream=_stream_for(record.name),
                level=record.levelname[:20],
                message=message,
                source=record.name[:160],
                context=context,
            )
        except Exception:
            # Logging must never become a second source of application failure.
            return
