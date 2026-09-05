from django.contrib.auth import get_user_model
from django.test import TestCase


PUBLIC_PAGES = [
    "/",
    "/login/",
    "/register/",
    "/terms/",
    "/privacy/",
    "/cookies/",
    "/licensing/",
    "/contact/",
    "/about/",
    "/data-deletion/",
    "/status/",
    "/forgot-password/",
    "/brokers/connect/",
    "/brokers/marketplace/",
]

AUTHENTICATED_PAGES = [
    "/dashboard/",
    "/billing/",
    "/saas/",
    "/markets/",
    "/market-scanner/",
    "/strategies/",
    "/strategies/builder/",
    "/trading/",
    "/backtesting/",
    "/predictions/",
    "/model-lab/",
    "/performance/",
    "/settings/",
    "/profile/",
    "/orders/",
    "/positions/",
    "/signals/",
    "/portfolio/",
    "/notifications/",
    "/analytics/",
    "/monitoring/",
    "/risk/",
    "/trade-history/",
    "/trade-history/postmortems/",
    "/automation/",
    "/operations/deployments/",
    "/operations/audit/",
    "/operations/security/",
    "/operations/brokers/",
    "/developer/",
    "/developer/keys/",
    "/smart-money/",
    "/analysis/",
    "/workspace/automation/",
    "/workspace/automation/workflow-templates/",
]


class BrowserPageSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="page-surface-test", password="test-pass"
        )

    def test_public_page_surface_renders(self):
        for path in PUBLIC_PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.content[:500])
                self.assertIn(b"<", response.content)

    def test_authenticated_page_surface_renders(self):
        self.client.force_login(self.user)
        for path in AUTHENTICATED_PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.content[:500])
                self.assertIn(b"<", response.content)
