"""Shared cache helpers for application modules."""

from django.core.cache import cache


def remember(key: str, value, timeout: int | None = None):
    """Store a value in the configured cache and return it for fluent use."""
    cache.set(key, value, timeout=timeout)
    return value
