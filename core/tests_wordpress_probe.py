from django.test import RequestFactory, SimpleTestCase
from django.http import HttpResponse

from core.middleware.wordpress_probe import (
    WordPressProbeLogFilter,
    WordPressProbeMiddleware,
)


class WordPressProbeMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_common_wordpress_paths_are_rejected(self):
        middleware = WordPressProbeMiddleware(lambda request: HttpResponse("ok"))
        for path in (
            "/wp/wp-json/batch/v1",
            "/wordpress/index.php?rest_route=/batch/v1",
            "/blog/wp/v2/posts/999998",
        ):
            response = middleware(self.factory.post(path))
            self.assertEqual(response.status_code, 404)

    def test_normal_application_paths_pass_through(self):
        middleware = WordPressProbeMiddleware(lambda request: HttpResponse("ok"))
        response = middleware(self.factory.get("/api/market/ticks/latest/?symbol=R_100"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_log_filter_drops_wordpress_probe_records(self):
        request = self.factory.get("/wordpress/wp-json/batch/v1")
        record = type("Record", (), {"request": request, "getMessage": lambda self: "Not Found"})()
        self.assertFalse(WordPressProbeLogFilter().filter(record))

    def test_log_filter_keeps_real_application_404s(self):
        request = self.factory.get("/api/market/ticks/latest/")
        record = type("Record", (), {"request": request, "getMessage": lambda self: "Not Found"})()
        self.assertTrue(WordPressProbeLogFilter().filter(record))
