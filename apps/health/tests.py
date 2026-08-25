from django.core.cache import cache
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
