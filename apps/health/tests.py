from django.core.cache import cache
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from . import views


class HealthEndpointTests(TestCase):
    def test_liveness_is_dependency_free(self):
        response = self.client.get(reverse("health:liveness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_render_health_is_dependency_free(self):
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "algobot")

    def test_health_endpoints_are_exempt_from_api_throttling(self):
        for endpoint in (views.health, views.liveness, views.readiness):
            self.assertEqual(endpoint.cls.throttle_classes, [])

    def test_render_probe_frequency_is_not_rate_limited(self):
        cache.clear()
        responses = [self.client.get(reverse("health:health")) for _ in range(101)]
        self.assertTrue(all(response.status_code == 200 for response in responses))

    def test_head_health_response_has_no_body(self):
        response = self.client.head(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    @patch("apps.health.views.cache.set", side_effect=RuntimeError("rediss://user:secret@redis.example:6379/0"))
    def test_readiness_reports_cache_write_failure_without_exposing_connection_details(self, cache_set):
        response = self.client.get(reverse("health:readiness"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["checks"]["database"])
        self.assertFalse(payload["checks"]["cache"])
        self.assertNotIn("secret", response.content.decode("utf-8"))
        cache_set.assert_called_once_with("healthcheck", "ok", 5)

    @patch("apps.health.views.cache.get", side_effect=RuntimeError("rediss://user:secret@redis.example:6379/0"))
    @patch("apps.health.views.cache.set", return_value=True)
    def test_readiness_reports_cache_read_failure_while_liveness_stays_available(self, cache_set, cache_get):
        ready = self.client.get(reverse("health:readiness"))
        live = self.client.get(reverse("health:health"))

        self.assertEqual(ready.status_code, 503)
        self.assertFalse(ready.json()["checks"]["cache"])
        self.assertEqual(live.status_code, 200)
        self.assertNotIn("secret", ready.content.decode("utf-8"))
        cache_set.assert_called_once()
        cache_get.assert_called_once_with("healthcheck")
