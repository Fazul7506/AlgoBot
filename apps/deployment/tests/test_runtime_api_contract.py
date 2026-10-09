from django.contrib.auth import get_user_model
from django.test import TestCase


class DeploymentApiSafetyTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="deployment-api-test", password="test-password")
        self.client.force_login(user)

    def test_deployment_and_backup_endpoints_fail_closed_when_provider_is_missing(self):
        for path in ("/api/deployment/deployment/", "/api/deployment/backups/", "/api/deployment/rollback/", "/api/deployment/restore/"):
            with self.subTest(path=path):
                response = self.client.post(path, data={}, content_type="application/json")
                self.assertEqual(response.status_code, 501)
                self.assertEqual(response.json()["status"], "not_configured")
                self.assertIn("no ", response.json()["detail"].lower())
