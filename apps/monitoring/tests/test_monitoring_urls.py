from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class MonitoringSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="monitoring-smoke", password="test-pass-123")
        self.client.force_login(self.user)

    def test_monitoring_page_resolves(self):
        response = self.client.get(reverse("monitoring-dashboard-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mission Control")

    def test_monitoring_api_resolves(self):
        response = self.client.get(reverse("monitoring-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("overall_system_health", response.json())
    def test_retired_backfill_page_routes_to_mission_control(self):
        response = self.client.get("/operations/candle-backfill/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mission Control")
        self.assertNotContains(response, "Start the backfill")

