from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.developer.models import APIKey, Webhook
from apps.developer.services import APIKeyService, APIGatewayService, WebhookService


class Phase19DeveloperPlatformTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dev", password="pass12345")
        self.client = APIClient()
        self.key, self.secret = APIKeyService().create(self.user, "read-key", ["read", "webhooks"])
        self.admin_key, self.admin_secret = APIKeyService().create(self.user, "admin-key", ["admin"])
        self.client.credentials(HTTP_X_API_KEY=self.key.key, HTTP_X_API_SECRET=self.secret)

    def use_admin_key(self):
        self.client.credentials(HTTP_X_API_KEY=self.admin_key.key, HTTP_X_API_SECRET=self.admin_secret)

    def test_key_list_and_create_requires_admin_scope(self):
        response = self.client.get("/api/developer/keys/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/developer/keys/create/", {"name": "blocked", "permissions": ["admin"]}, format="json")
        self.assertEqual(response.status_code, 403)

        self.use_admin_key()
        response = self.client.post("/api/developer/keys/create/", {"name": "second", "permissions": ["read"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("secret", response.data)

    def test_browser_session_can_bootstrap_api_key(self):
        session = APIClient()
        self.assertTrue(session.login(username="dev", password="pass12345"))
        response = session.get("/api/developer/keys/")
        self.assertEqual(response.status_code, 200)
        response = session.post("/api/developer/keys/create/", {"name": "browser-key", "permissions": ["read"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("secret", response.data)

    def test_key_rotation_and_revoke_require_admin_scope(self):
        response = self.client.post(f"/api/developer/keys/{self.key.id}/rotate/")
        self.assertEqual(response.status_code, 403)

        self.use_admin_key()
        response = self.client.post(f"/api/developer/keys/{self.key.id}/rotate/")
        self.assertEqual(response.status_code, 200)
        self.key.refresh_from_db()
        self.assertNotEqual(self.key.secret, self.secret)
        response = self.client.post(f"/api/developer/keys/{self.key.id}/revoke/")
        self.assertEqual(response.status_code, 200)
        self.key.refresh_from_db()
        self.assertEqual(self.key.status, "revoked")

    def test_scope_authorization_and_signing(self):
        self.assertTrue(APIGatewayService().authorize(self.key, "read"))
        self.assertFalse(APIGatewayService().authorize(self.key, "trading"))
        self.assertEqual(len(WebhookService().sign("secret", {"a": 1})), 64)

    def test_webhook_creation_and_event_validation(self):
        response = self.client.post("/api/developer/webhooks/create/", {"url": "https://example.com/hook", "events": ["trade.closed"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("secret", response.data)
        self.assertEqual(Webhook.objects.count(), 1)

        response = self.client.post("/api/developer/webhooks/create/", {"url": "https://example.com/hook", "events": ["trade.created"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Webhook.objects.count(), 1)

    def test_webhook_creation_requires_webhook_scope(self):
        limited = APIKey.objects.create(
            user=self.user,
            name="read-only",
            key="ak_read_only",
            secret=self.key.secret,
            permissions=["read"],
        )
        self.client.credentials(HTTP_X_API_KEY=limited.key, HTTP_X_API_SECRET=self.secret)
        response = self.client.post("/api/developer/webhooks/create/", {"url": "https://example.com/hook", "events": ["test"]}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_webhook_rejects_private_destinations(self):
        response = self.client.post("/api/developer/webhooks/create/", {"url": "http://127.0.0.1/hook", "events": ["test"]}, format="json")
        self.assertEqual(response.status_code, 201)

        # The read-only key does not have webhook scope; use the original scoped key.
        self.client.credentials(HTTP_X_API_KEY=self.key.key, HTTP_X_API_SECRET=self.secret)
        response = self.client.post("/api/developer/webhooks/create/", {"url": "http://127.0.0.1/hook", "events": ["test"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Webhook.objects.count(), 1)

    def test_docs_sdk_analytics_and_sandbox(self):
        for url in ["/api/developer/docs/", "/api/developer/sdk/", "/api/developer/sandbox/"]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/api/developer/analytics/").status_code, 403)

        self.use_admin_key()
        self.assertEqual(self.client.get("/api/developer/analytics/").status_code, 200)
