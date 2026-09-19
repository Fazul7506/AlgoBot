from pathlib import Path

from django.conf import settings
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
            "/analysis/",
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


    def test_sidebar_has_chat_workspace_collapse_contract(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="app-sidebar"')
        self.assertContains(response, 'data-sidebar-toggle')
        self.assertContains(response, 'aria-label="Collapse navigation"')
        self.assertContains(response, 'aria-expanded="true"')
        for href in (
            "/dashboard/", "/trading/", "/markets/", "/orders/", "/trade-history/",
            "/positions/", "/signals/", "/strategies/", "/backtesting/", "/performance/",
            "/predictions/", "/analysis/", "/risk/", "/monitoring/", "/notifications/",
            "/automation/", "/operations/deployments/", "/operations/audit/",
            "/operations/security/", "/portfolio/", "/operations/brokers/", "/billing/",
            "/developer/",
        ):
            with self.subTest(href=href):
                self.assertContains(response, f'href="{href}"')

    def test_universal_workspace_links_are_present_in_authenticated_sidebar(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        for label, href in (
            ("Analysis", "/analysis/"),
            ("Notifications", "/notifications/"),
            ("Bot Runtime", "/operations/deployments/"),
            ("Audit Log", "/operations/audit/"),
            ("Security Center", "/operations/security/"),
            ("Developer & API", "/developer/"),
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, f'href="{href}"')


    def test_authenticated_shell_uses_vertical_topbar_content_flow(self):
        """The current sibling DOM must not be laid out as the legacy flex-row shell."""
        css_path = Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".app-shell {\n  display: block !important;", css)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260919-shellflow1")
