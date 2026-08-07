"""Structured, rotating logging configuration for AlgoBot."""

from .base import BASE_DIR
from .utils import env

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
SENTRY_DSN = env("SENTRY_DSN", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}", "style": "{"},
        "json": {
            "format": '{"level":"{levelname}","time":"{asctime}","logger":"{name}","module":"{module}","message":"{message}"}',
            "style": "{",
        },
    },
    "handlers": {
        "console": {"level": "INFO", "class": "logging.StreamHandler", "formatter": "verbose"},
        "django_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "django.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "oauth_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "oauth.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "broker_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "broker.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "trading_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "trading.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "websocket_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "websocket.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "monitoring_file": {"level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "monitoring.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
        "error_file": {"level": "ERROR", "class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "errors.log", "maxBytes": 10485760, "backupCount": 10, "formatter": "json"},
    },
    "root": {"handlers": ["console", "django_file", "error_file"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console", "django_file", "error_file"], "level": "INFO", "propagate": False},
        "oauth": {"handlers": ["oauth_file", "error_file"], "level": "INFO", "propagate": True},
        "broker": {"handlers": ["broker_file", "error_file"], "level": "INFO", "propagate": True},
        "market": {"handlers": ["trading_file"], "level": "INFO", "propagate": True},
        "trading": {"handlers": ["trading_file", "error_file"], "level": "INFO", "propagate": True},
        "websocket": {"handlers": ["websocket_file", "error_file"], "level": "INFO", "propagate": True},
        "monitoring": {"handlers": ["monitoring_file", "error_file"], "level": "INFO", "propagate": True},
        "ai": {"handlers": ["trading_file"], "level": "INFO", "propagate": True},
        "security": {"handlers": ["django_file", "error_file"], "level": "INFO", "propagate": True},
    },
}
