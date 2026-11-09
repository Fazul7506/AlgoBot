from django.core.cache import cache
from unittest.mock import patch

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

    @patch.dict("os.environ", {"RENDER_GIT_COMMIT": "a" * 40})
    def test_render_health_exposes_only_the_deployed_commit_identifier(self):
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["commit"], "a" * 40)

    @patch.dict("os.environ", {"RENDER_GIT_COMMIT": "not-a-commit-secret"})
    def test_render_health_omits_invalid_deploy_metadata(self):
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("commit", response.json())

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

    @patch("apps.health.views.cache.set", side_effect=RuntimeError("rediss://user:secret@redis.example:6379/0"))
    def test_readiness_reports_cache_write_failure_without_exposing_connection_details(self, cache_set):
        response = self.client.get(reverse("health:readiness"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["checks"]["database"])
        self.assertFalse(payload["checks"]["cache"])
        self.assertNotIn("secret", response.content.decode("utf-8"))
        cache_set.assert_called_once_with("healthcheck", "ok", 5)

    @patch("apps.health.views.cache.get", side_effect=RuntimeError("rediss://user:secret@redis.example:6379/0"))
    @patch("apps.health.views.cache.set", return_value=True)
    def test_readiness_reports_cache_read_failure_while_liveness_stays_available(self, cache_set, cache_get):
        ready = self.client.get(reverse("health:readiness"))
        live = self.client.get(reverse("health:health"))

        self.assertEqual(ready.status_code, 503)
        self.assertFalse(ready.json()["checks"]["cache"])
        self.assertEqual(live.status_code, 200)
        self.assertNotIn("secret", ready.content.decode("utf-8"))
        cache_set.assert_called_once()
        cache_get.assert_called_once_with("healthcheck")


class SensitiveFileProbeMiddlewareTests(TestCase):
    def test_sensitive_file_scans_are_rejected_before_application_routing(self):
        paths = (
            "/.env",
            "/.env.production",
            "/.aws/credentials",
            "/.git/config",
            "/.docker/.env",
            "/.cursor/mcp.json",
            "/.claude/settings.local.json",
            "/admin/.env",
            "/api/.env",
            "/env.txt",
            "/actuator/env",
            "/api/actuator/env",
            "/appsettings.Production.json",
            "/config/config.js",
            "/credentials.json",
            "/secrets.json",
            "/.gitlab-ci.yml",
        )

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.content, b"Not found")
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_encoded_secret_probe_paths_are_rejected(self):
        for path in ("/.%65nv", "/%2eenv.production", "/%252eenv.backup"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_probe_guard_does_not_intercept_application_or_health_routes(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get("/login/").status_code, 200)

    def test_probe_guard_rejects_non_get_methods_too(self):
        response = self.client.post("/.env", data={"probe": "ignored"})
        self.assertEqual(response.status_code, 404)
