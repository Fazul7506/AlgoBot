from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from redis.exceptions import OutOfMemoryError, ConnectionError

from core import auth_rate_limit


class AuthRateLimitCacheFailureTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().post("/login/", REMOTE_ADDR="192.0.2.10")
        auth_rate_limit._fallback_cache.clear()

    def tearDown(self):
        auth_rate_limit._fallback_cache.clear()

    @patch("core.auth_rate_limit.cache.add", side_effect=RuntimeError("redis backend unavailable"))
    def test_shared_cache_failure_uses_bounded_local_fallback(self, cache_add):
        with self.assertLogs("account_auth", level="ERROR") as captured:
            self.assertTrue(
                auth_rate_limit.allow_auth_attempt(
                    self.request, "login", "person@example.test", limit=2, window=60
                )
            )

        self.assertTrue(any("error_type=RuntimeError" in entry for entry in captured.output))
        self.assertFalse(any("redis backend unavailable" in entry for entry in captured.output))
        cache_add.assert_called_once()

    @patch("core.auth_rate_limit.cache.add", side_effect=RuntimeError("redis backend unavailable"))
    def test_local_fallback_still_enforces_limit_during_cache_outage(self, _cache_add):
        self.assertTrue(
            auth_rate_limit.allow_auth_attempt(
                self.request, "login", "person@example.test", limit=2, window=60
            )
        )
        self.assertTrue(
            auth_rate_limit.allow_auth_attempt(
                self.request, "login", "person@example.test", limit=2, window=60
            )
        )
        self.assertFalse(
            auth_rate_limit.allow_auth_attempt(
                self.request, "login", "person@example.test", limit=2, window=60
            )
        )

    @patch("core.auth_rate_limit.cache.add", side_effect=OutOfMemoryError("rediss://user:secret@redis.example:6379/0"))
    def test_redis_maxmemory_write_failure_uses_bounded_fallback_without_leaking_url(self, cache_add):
        with self.assertLogs("account_auth", level="ERROR") as captured:
            self.assertTrue(
                auth_rate_limit.allow_auth_attempt(
                    self.request, "login", "person@example.test", limit=2, window=60
                )
            )

        self.assertEqual(captured.records[0].error_type, "OutOfMemoryError")
        self.assertFalse(any("secret" in entry or "rediss://" in entry for entry in captured.output))
        cache_add.assert_called_once()

    @patch("core.auth_rate_limit.cache.incr", side_effect=ConnectionError("rediss://user:secret@redis.example:6379/0"))
    @patch("core.auth_rate_limit.cache.add", return_value=False)
    def test_redis_read_failure_uses_bounded_fallback_without_leaking_url(self, cache_add, cache_incr):
        with self.assertLogs("account_auth", level="ERROR") as captured:
            self.assertTrue(
                auth_rate_limit.allow_auth_attempt(
                    self.request, "login", "person@example.test", limit=2, window=60
                )
            )

        self.assertEqual(captured.records[0].error_type, "ConnectionError")
        self.assertFalse(any("secret" in entry or "rediss://" in entry for entry in captured.output))
        cache_add.assert_called_once()
        cache_incr.assert_called_once()
