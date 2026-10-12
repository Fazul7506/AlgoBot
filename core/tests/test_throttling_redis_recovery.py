"""Regression tests for Redis exhaustion in DRF throttling."""
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from redis.exceptions import OutOfMemoryError
from rest_framework.throttling import AnonRateThrottle

from core import throttling


class RedisThrottleRecoveryTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/api/auth/browser-token/")
        self.view = object()
        throttling._redis_unavailable_until = 0.0
        throttling._fallback_cache.clear()

    def tearDown(self):
        throttling._redis_unavailable_until = 0.0
        throttling._fallback_cache.clear()

    def test_redis_out_of_memory_uses_local_fallback_instead_of_raising(self):
        with patch.object(AnonRateThrottle, "allow_request", side_effect=OutOfMemoryError("maxmemory exceeded")), patch.object(
            throttling.ResilientAnonRateThrottle,
            "_allow_with_cache",
            return_value=True,
        ) as fallback:
            allowed = throttling.ResilientAnonRateThrottle().allow_request(self.request, self.view)

        self.assertTrue(allowed)
        fallback.assert_called_once_with(self.request, throttling._fallback_cache)
        self.assertGreater(throttling._redis_unavailable_until, throttling.monotonic())

    def test_circuit_cooldown_avoids_repeated_redis_calls(self):
        throttling._redis_unavailable_until = throttling.monotonic() + 30
        with patch.object(AnonRateThrottle, "allow_request", side_effect=AssertionError("Redis should be bypassed")), patch.object(
            throttling.ResilientAnonRateThrottle,
            "_allow_with_cache",
            return_value=True,
        ) as fallback:
            allowed = throttling.ResilientAnonRateThrottle().allow_request(self.request, self.view)

        self.assertTrue(allowed)
        fallback.assert_called_once_with(self.request, throttling._fallback_cache)

    def test_successful_redis_request_resets_circuit_breaker(self):
        throttling._redis_unavailable_until = throttling.monotonic() + 30
        # Expire the cooldown and exercise the normal DRF path.
        throttling._redis_unavailable_until = 0.0
        with patch.object(AnonRateThrottle, "allow_request", return_value=True):
            allowed = throttling.ResilientAnonRateThrottle().allow_request(self.request, self.view)

        self.assertTrue(allowed)
        self.assertEqual(throttling._redis_unavailable_until, 0.0)
