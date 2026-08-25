from django.test import SimpleTestCase

from deriv_platform.settings import deployment_environment


class DeploymentEnvironmentTests(SimpleTestCase):
    def test_render_defaults_to_production_settings(self):
        self.assertEqual(deployment_environment({"RENDER": "true"}), "production")

    def test_explicit_environment_takes_precedence_over_render_default(self):
        self.assertEqual(
            deployment_environment({"RENDER": "true", "DJANGO_ENV": "development"}),
            "development",
        )

    def test_local_process_defaults_to_development_settings(self):
        self.assertEqual(deployment_environment({}), "development")
