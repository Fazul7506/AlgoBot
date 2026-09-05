from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver


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
]

AUTHENTICATED_PAGES = [
    "/dashboard/", "/billing/", "/billing/success/", "/billing/cancel/",
    "/brokers/marketplace/", "/saas/", "/markets/", "/market-scanner/",
    "/strategies/", "/strategies/builder/", "/trading/", "/backtesting/",
    "/predictions/", "/model-lab/", "/performance/", "/settings/", "/profile/",
    "/orders/", "/positions/", "/signals/", "/portfolio/", "/notifications/",
    "/analytics/", "/monitoring/", "/monitoring/ui/", "/risk/", "/trade-history/",
    "/trade-history/postmortems/", "/automation/", "/operations/deployments/",
    "/operations/audit/", "/operations/security/", "/operations/brokers/",
    "/developer/", "/developer/keys/", "/smart-money/", "/smart-money/heatmap/",
    "/analysis/", "/workspace/automation/", "/workspace/automation/workflow-templates/",
]


def static_browser_routes():
    """Discover every parameter-free, non-API GET route from Django URLconf."""
    routes = set()

    def walk(patterns, prefix=""):
        for entry in patterns:
            if isinstance(entry, URLResolver):
                route = str(getattr(entry.pattern, "_route", ""))
                if route and "<" not in route:
                    walk(entry.url_patterns, prefix + route)
            elif isinstance(entry, URLPattern):
                route = str(getattr(entry.pattern, "_route", ""))
                full = (prefix + route).replace("//", "/")
                if "<" in full or full.startswith("/api/") or "api/" in full.split("/", 2)[0:1]:
                    continue
                callback = getattr(entry, "callback", None)
                methods = getattr(callback, "actions", None) or getattr(callback, "http_method_names", None)
                if methods is not None and "get" not in [str(m).lower() for m in methods]:
                    continue
                routes.add("/" + full.strip("/") + "/" if full.strip("/") else "/")

    walk(get_resolver().url_patterns)
    return sorted(routes)


class BrowserPageSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="page-surface-test", password="test-pass"
        )

    def assert_html_response(self, path, response):
        self.assertLess(response.status_code, 500, f"{path} returned {response.status_code}: {response.content[:500]!r}")
        content_type = response.headers.get("Content-Type", "").lower()
        if response.status_code == 200:
            self.assertIn("text/html", content_type, f"{path} did not render HTML")
            self.assertIn(b"<", response.content)

    def test_public_page_surface_renders(self):
        for path in PUBLIC_PAGES:
            with self.subTest(path=path):
                self.assert_html_response(path, self.client.get(path))

    def test_authenticated_page_surface_renders(self):
        self.client.force_login(self.user)
        for path in AUTHENTICATED_PAGES:
            with self.subTest(path=path):
                self.assert_html_response(path, self.client.get(path))

    def test_every_static_django_browser_route_is_smoke_tested(self):
        self.client.force_login(self.user)
        routes = static_browser_routes()
        self.assertGreaterEqual(len(routes), len(PUBLIC_PAGES) + len(AUTHENTICATED_PAGES) - 5)
        for path in routes:
            with self.subTest(path=path):
                self.assert_html_response(path, self.client.get(path))
