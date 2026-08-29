from django.contrib.auth import get_user_model
from django.test import TestCase


class UniversalWorkspaceAccessTests(TestCase):
    """Regression coverage: operational/developer workspaces are not Enterprise-only."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="free-workspace-user", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_operations_and_developer_pages_are_available_to_authenticated_users(self):
        routes = (
            "/operations/mission-control/",
            "/notifications/",
            "/operations/deployments/",
            "/operations/audit/",
            "/operations/security/",
            "/developer/",
        )
        for path in routes:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotEqual(response.status_code, 302, path)
                self.assertEqual(response.status_code, 200, path)

    def test_legacy_alert_center_redirects_to_notifications(self):
        response = self.client.get("/operations/alerts/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/notifications/")

    def test_universal_workspace_links_are_present_in_authenticated_sidebar(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        for label, href in (
            ("Mission Control", "/operations/mission-control/"),
            ("Notifications", "/notifications/"),
            ("Bot Runtime", "/operations/deployments/"),
            ("Audit Log", "/operations/audit/"),
            ("Security Center", "/operations/security/"),
            ("Developer & API", "/developer/"),
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, f'href="{href}"')
