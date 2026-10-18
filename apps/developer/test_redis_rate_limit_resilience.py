"""Regression tests for developer API rate limiting during Redis quota incidents."""
from unittest.mock import patch

from django.test import SimpleTestCase
from redis.exceptions import OutOfMemoryError

from apps.developer import middleware


class DeveloperRateLimitRedisRecoveryTests(SimpleTestCase):
    def setUp(self):
        middleware._fallback_rate_limit_cache.clear()
        middleware._redis_unavailable_until = 0.0

    def tearDown(self):
        middleware._fallback_rate_limit_cache.clear()
        middleware._redis_unavailable_until = 0.0

    def test_redis_out_of_memory_uses_local_rate_limit_counter(self):
        key = "test:developer-rate-limit"

        with patch.object(
            middleware.cache,
            "incr",
            side_effect=OutOfMemoryError("maxmemory exceeded"),
        ):
            self.assertEqual(middleware._next_rate_limit_count(key, 60), 1)

        self.assertGreater(
            middleware._redis_unavailable_until,
            middleware.time.monotonic(),
        )
        self.assertEqual(
            middleware._next_rate_limit_count(key, 60),
            2,
            "Requests during the cooldown should stay on the local fallback.",
        )

    def test_raw_redis_oom_enters_fallback_cooldown(self):
        from django.conf import settings

        with patch.object(settings, "USE_REDIS", True), patch(
            "django_redis.get_redis_connection"
        ) as get_connection:
            get_connection.return_value.incr.side_effect = OutOfMemoryError(
                "maxmemory exceeded"
            )
            self.assertEqual(
                middleware._next_rate_limit_count("test:raw-redis", 60), 1
            )

        self.assertGreater(
            middleware._redis_unavailable_until,
            middleware.time.monotonic(),
        )
        self.assertEqual(
            middleware._next_rate_limit_count("test:raw-redis", 60), 2
        )

    def test_open_circuit_does_not_call_redis(self):
        key = "test:developer-rate-limit"
        middleware._redis_unavailable_until = middleware.time.monotonic() + 30

        with patch.object(
            middleware.cache,
            "incr",
            side_effect=AssertionError("Redis must be bypassed during cooldown"),
        ), patch.object(
            middleware.cache,
            "add",
            side_effect=AssertionError("Redis must be bypassed during cooldown"),
        ):
            self.assertEqual(middleware._next_rate_limit_count(key, 60), 1)
            self.assertEqual(middleware._next_rate_limit_count(key, 60), 2)

    def test_redis_existing_counter_uses_one_raw_increment(self):
        from django.conf import settings

        with patch.object(settings, "USE_REDIS", True), patch(
            "django_redis.get_redis_connection"
        ) as get_connection:
            redis_client = get_connection.return_value
            redis_client.incr.return_value = 7
            count = middleware._increment_rate_counter(
                middleware.cache, "counter", 60
            )

        self.assertEqual(count, 7)
        redis_client.incr.assert_called_once_with(
            middleware.cache.make_key("counter")
        )
        redis_client.expire.assert_not_called()

    def test_redis_first_counter_increment_sets_expiry(self):
        from django.conf import settings

        with patch.object(settings, "USE_REDIS", True), patch(
            "django_redis.get_redis_connection"
        ) as get_connection:
            redis_client = get_connection.return_value
            redis_client.incr.return_value = 1
            count = middleware._increment_rate_counter(
                middleware.cache, "counter", 60
            )

        self.assertEqual(count, 1)
        redis_client.expire.assert_called_once_with(
            middleware.cache.make_key("counter"), 60
        )

    def test_existing_counter_uses_one_increment_without_add(self):
        class ExistingCounterBackend:
            def __init__(self):
                self.add_calls = 0
                self.incr_calls = 0

            def incr(self, key):
                self.incr_calls += 1
                return 7

            def add(self, key, value, timeout):
                self.add_calls += 1
                return False

        backend = ExistingCounterBackend()
        self.assertEqual(
            middleware._increment_rate_counter(backend, "counter", 60),
            7,
        )
        self.assertEqual(backend.incr_calls, 1)
        self.assertEqual(backend.add_calls, 0)

    def test_expired_counter_is_recreated_with_its_ttl(self):
        class ExpiringBackend:
            def __init__(self):
                self.add_calls = 0
                self.incr_calls = 0

            def add(self, key, value, timeout):
                self.add_calls += 1
                return self.add_calls == 2

            def incr(self, key):
                self.incr_calls += 1
                raise ValueError("key expired")

        backend = ExpiringBackend()
        self.assertEqual(
            middleware._increment_rate_counter(backend, "counter", 60),
            1,
        )
        self.assertEqual(backend.add_calls, 2)
