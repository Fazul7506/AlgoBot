from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.monitoring.models import LogEntry


class MonitoringSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="monitoring-smoke", password="test-pass-123")
        self.client.force_login(self.user)

    def test_monitoring_page_resolves(self):
        response = self.client.get(reverse("monitoring-dashboard-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoring")

    def test_monitoring_api_resolves(self):
        response = self.client.get(reverse("monitoring-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("overall_system_health", response.json())

    def test_mission_control_is_staff_only(self):
        response = self.client.get(reverse("mission-control"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_staff_mission_control_is_separate_from_monitoring(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.get(reverse("mission-control"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mission Control")
        monitoring = self.client.get(reverse("monitoring-dashboard-page"))
        self.assertContains(monitoring, "Monitoring")

    def test_mission_event_feed_filters_by_severity_area_and_search(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        LogEntry.objects.create(stream="application", level="INFO", message="Healthy request completed", source="api")
        LogEntry.objects.create(stream="broker", level="ERROR", message="Historical broker request failed", source="deriv")
        response = self.client.get(
            "/api/monitoring/mission-events/?level=ERROR&stream=broker&search=historical"
        )
        self.assertEqual(response.status_code, 200)
        events = response.json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["level"], "ERROR")
        self.assertEqual(events[0]["stream"], "broker")
        self.assertIn("Historical", events[0]["message"])
