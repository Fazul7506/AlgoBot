"""Redis-resilient DRF throttles.

Rate limiting is useful policy, but a Redis client-exhaustion incident must not
turn every authenticated API request into an HTTP 500. These throttles keep the
same DRF rate policy and use a process-local emergency bucket only while the
shared cache is unavailable.
"""
from __future__ import annotations

import logging
from time import time

from django.core.cache.backends.locmem import LocMemCache
from django_redis.exceptions import ConnectionInterrupted
from redis.exceptions import ConnectionError as RedisConnectionError

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)
_fallback_cache = LocMemCache("algobot-throttle-fallback", {})


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
        self.view = view
        try:
            return super().allow_request(request, view)
        except (ConnectionInterrupted, RedisConnectionError, TimeoutError, OSError):
            logger.warning(
                "redis_throttle_cache_unavailable",
                extra={"throttle": self.__class__.__name__},
            )
            return self._allow_with_cache(request, _fallback_cache)


class ResilientAnonRateThrottle(_RedisResilientThrottleMixin, AnonRateThrottle):
    """Anonymous request throttle with a local emergency fallback."""


class ResilientUserRateThrottle(_RedisResilientThrottleMixin, UserRateThrottle):
    """Authenticated request throttle with a local emergency fallback."""
