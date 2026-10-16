"""Regression tests for auth throttling during shared-cache outages."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase

from core.auth_rate_limit import _fallback_cache, allow_auth_attempt


class AuthRateLimitFallbackTests(SimpleTestCase):
    def setUp(self):
        _fallback_cache.clear()
        self.request = RequestFactory().post("/login/")
        self.request.META["REMOTE_ADDR"] = "192.0.2.91"

    def tearDown(self):
        _fallback_cache.clear()
        cache.clear()

    @patch("core.auth_rate_limit.cache.add", side_effect=RuntimeError("cache unavailable"))
    def test_shared_cache_outage_uses_bounded_process_fallback(self, _shared_add):
        self.assertTrue(
            allow_auth_attempt(
                self.request, "fallback-regression", "cache-down@example.test", limit=1, window=60
            )
        )
        self.assertFalse(
            allow_auth_attempt(
                self.request, "fallback-regression", "cache-down@example.test", limit=1, window=60
            )
        )

    @patch("core.auth_rate_limit.cache.add", side_effect=RuntimeError("do not log this backend detail"))
    def test_cache_failure_logs_exception_type_without_backend_error_text(self, _shared_add):
        with self.assertLogs("account_auth", level="ERROR") as captured:
            self.assertTrue(
                allow_auth_attempt(
                    self.request, "safe-diagnostic", "cache-down@example.test", limit=2, window=60
                )
            )

        self.assertIn("error_type=RuntimeError", captured.output[0])
        self.assertNotIn("do not log this backend detail", captured.output[0])
