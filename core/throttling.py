"""Redis-resilient DRF throttles with a fail-fast circuit breaker.

Rate limiting remains enabled when Redis is healthy. If the shared Redis cache
is unavailable or exhausted, the API must not wait on Redis for every request
or turn cache pressure into a page-wide loading failure. A short process-local
cooldown routes throttling to an emergency in-memory bucket until Redis is
healthy again.
"""
from __future__ import annotations

import logging
from time import monotonic

from django.core.cache.backends.locmem import LocMemCache
from django_redis.exceptions import ConnectionInterrupted
from redis.exceptions import ConnectionError as RedisConnectionError

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)
_fallback_cache = LocMemCache("algobot-throttle-fallback", {})
_REDIS_FAILURE_COOLDOWN_SECONDS = 30.0
_redis_unavailable_until = 0.0


class _RedisResilientThrottleMixin:
    def _allow_with_cache(self, request, cache):
        self.key = self.get_cache_key(request, self.view)
        if self.key is None:
            return True

        self.history = cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            return False

        self.history.insert(0, self.now)
        cache.set(self.key, self.history, self.duration)
        return True

    def allow_request(self, request, view):
        global _redis_unavailable_until
        self.view = view
        if monotonic() < _redis_unavailable_until:
            return self._allow_with_cache(request, _fallback_cache)

        try:
            allowed = super().allow_request(request, view)
            _redis_unavailable_until = 0.0
            return allowed
        except (ConnectionInterrupted, RedisConnectionError, TimeoutError, OSError):
            now = monotonic()
            was_open = now >= _redis_unavailable_until
            _redis_unavailable_until = now + _REDIS_FAILURE_COOLDOWN_SECONDS
            if was_open:
                logger.warning(
                    "redis_throttle_cache_unavailable",
                    extra={
                        "throttle": self.__class__.__name__,
                        "fallback_cooldown_seconds": _REDIS_FAILURE_COOLDOWN_SECONDS,
                    },
                )
            return self._allow_with_cache(request, _fallback_cache)


class ResilientAnonRateThrottle(_RedisResilientThrottleMixin, AnonRateThrottle):
    """Anonymous request throttle with a local emergency fallback."""


class ResilientUserRateThrottle(_RedisResilientThrottleMixin, UserRateThrottle):
    """Authenticated request throttle with a local emergency fallback."""
