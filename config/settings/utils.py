"""Environment parsing helpers for AlgoBot settings."""

from __future__ import annotations

import os
from typing import Iterable


def env(name: str, default: str = "") -> str:
    """Return a string environment variable with a safe default."""
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    """Return a boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: Iterable[str] = ()) -> list[str]:
    """Return a comma-separated environment variable as a list."""
    value = os.getenv(name)
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def deployment_cookie_domain(name: str, default: str, *, preview: bool | None = None) -> str | None:
    """Return the cookie domain for the deployment's public browser origin.

    Render assigns an ``*.onrender.com`` hostname to ordinary production
    services as well as preview services. That hostname therefore cannot be
    used to infer preview status. Only an explicit preview flag may disable
    the shared production cookie domain needed by the UI/API subdomains.
    """
    if preview is None:
        preview = env_bool("ALGOBOT_PREVIEW_DEPLOYMENT", False)
    if preview:
        return None
    return os.getenv(name, default) or None


def validate_required_settings(*, production: bool, values: dict[str, str]) -> None:
    """Raise a clear error when production-critical configuration is missing."""
    if not production:
        return
    missing = [name for name, value in values.items() if not str(value or "").strip()]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required production configuration: {joined}")
