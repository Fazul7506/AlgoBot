from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness_is_dependency_free(self):
        response = self.client.get(reverse("health:liveness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_render_health_is_dependency_free(self):
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "algobot")
