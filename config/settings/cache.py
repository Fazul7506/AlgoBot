"""Cache settings for AlgoBot.

Redis configuration may be supplied through the process environment or through
the local .env/.env.production files.  Only cache/worker variables are read
from dotenv files here so loading a developer .env cannot silently switch the
database or Django environment used by management commands/tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

from .base import BASE_DIR
from .utils import env, env_bool


def _dotenv_value(name: str, default: str = "") -> str:
    """Return an env value, falling back to a dotenv file when unset."""
    value = os.getenv(name)
    if value is not None:
        return value

    candidates = [BASE_DIR / ".env"]
    if os.getenv("DJANGO_ENV", "").strip().lower() == "production":
        candidates.insert(0, BASE_DIR / ".env.production")

    for path in candidates:
        if path.exists():
            loaded = dotenv_values(path).get(name)
            if loaded is not None:
                return str(loaded)

    return default


REDIS_URL = _dotenv_value("REDIS_URL", "redis://localhost:6379/0")
USE_REDIS = _dotenv_value("USE_REDIS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CELERY_BROKER_URL = _dotenv_value("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = _dotenv_value("CELERY_RESULT_BACKEND", REDIS_URL)

CACHES = {
    "default": {
        "BACKEND": (
            "django_redis.cache.RedisCache"
            if USE_REDIS
            else "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": REDIS_URL if USE_REDIS else "unique-deriv-platform",
        "OPTIONS": (
            {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "socket_connect_timeout": 5,
                    "socket_timeout": 5,
                },
            }
            if USE_REDIS
            else {}
        ),
    }
}
