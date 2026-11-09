from django.test import SimpleTestCase, override_settings


class SensitivePathProbeMiddlewareTests(SimpleTestCase):
    @override_settings(MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "core.middleware.wordpress_probe.WordPressProbeMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ])
    def test_secret_and_configuration_probes_are_rejected_before_admin_routing(self):
        from django.test import Client

        client = Client()
        paths = (
            "/.env", "/.env.production", "/.aws/credentials", "/.git/config",
            "/.docker/config.json", "/admin/.env", "/actuator/env",
            "/api/actuator/env", "/Dockerfile", "/docker-compose.yml",
            "/phpinfo.php", "/storage/logs/laravel.log",
        )
        for path in paths:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_well_known_resources_are_not_classified_as_secret_probes(self):
        from core.middleware.wordpress_probe import WordPressProbeMiddleware

        self.assertFalse(
            WordPressProbeMiddleware.is_sensitive_path("/.well-known/security.txt")
        )

    def test_normal_application_paths_are_not_blocked(self):
        from core.middleware.wordpress_probe import WordPressProbeMiddleware

        self.assertFalse(WordPressProbeMiddleware.is_sensitive_path("/dashboard/"))
        self.assertFalse(WordPressProbeMiddleware.is_sensitive_path("/api/health/"))
