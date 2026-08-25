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


# Backwards-compatible names used by the base settings module and older
# settings consumers. Keep these aliases so the settings API remains stable
# while env_bool/env_list are the canonical helper names.
get_bool_env = env_bool
get_list_env = env_list


def validate_required_settings(*, production: bool, values: dict[str, str]) -> None:
    """Raise a clear error when production-critical configuration is missing."""
    if not production:
        return
    missing = [name for name, value in values.items() if not str(value or "").strip()]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required production configuration: {joined}")
