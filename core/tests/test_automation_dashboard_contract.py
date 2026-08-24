from django.contrib.auth import get_user_model
from django.test import TestCase


class AutomationDashboardContractTests(TestCase):
    def test_automation_dashboard_starts_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("automation-owner", "automation@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get("/workspace/automation/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker-aware automation", content)
        self.assertIn("Connect a broker", content)
