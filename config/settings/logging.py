"""Logging configuration for AlgoBot."""

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
    },
    "handlers": {
        "console": {"level": "INFO", "class": "logging.StreamHandler", "formatter": "verbose"},
        "application_file": {"level": "DEBUG", "class": "logging.FileHandler", "filename": LOG_DIR / "application.log", "formatter": "verbose"},
        "error_file": {"level": "ERROR", "class": "logging.FileHandler", "filename": LOG_DIR / "error.log", "formatter": "verbose"},
    },
    "root": {"handlers": ["console", "application_file", "error_file"], "level": "DEBUG"},
    "loggers": {
        "broker": {"handlers": ["application_file"], "level": "INFO", "propagate": True},
        "market": {"handlers": ["application_file"], "level": "INFO", "propagate": True},
        "trading": {"handlers": ["application_file"], "level": "INFO", "propagate": True},
        "ai": {"handlers": ["application_file"], "level": "INFO", "propagate": True},
        "security": {"handlers": ["application_file", "error_file"], "level": "INFO", "propagate": True},
    },
}
