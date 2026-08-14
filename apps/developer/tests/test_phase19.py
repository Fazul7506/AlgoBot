from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.developer.models import APIKey, Webhook
from apps.developer.services import APIKeyService, APIGatewayService, WebhookService

class Phase19DeveloperPlatformTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dev", password="pass12345")
        self.client = APIClient()
        self.key, self.secret = APIKeyService().create(self.user, "test", ["read", "webhooks"])
        self.client.credentials(HTTP_X_API_KEY=self.key.key, HTTP_X_API_SECRET=self.secret)

    def test_key_list_and_create(self):
        response = self.client.get("/api/developer/keys/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/developer/keys/", {"name": "second", "permissions": ["read"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("secret", response.data)

    def test_key_rotation_and_revoke(self):
        response = self.client.post(f"/api/developer/keys/{self.key.id}/rotate/")
        self.assertEqual(response.status_code, 200)
        self.key.refresh_from_db(); self.assertNotEqual(self.key.secret, self.secret)
        response = self.client.post(f"/api/developer/keys/{self.key.id}/revoke/")
        self.assertEqual(response.status_code, 200)
        self.key.refresh_from_db(); self.assertEqual(self.key.status, "revoked")

    def test_scope_authorization_and_signing(self):
        self.assertTrue(APIGatewayService().authorize(self.key, "read"))
        self.assertFalse(APIGatewayService().authorize(self.key, "trading"))
        self.assertEqual(len(WebhookService().sign("secret", {"a": 1})), 64)

    def test_webhook_creation(self):
        response = self.client.post("/api/developer/webhooks/", {"url": "https://example.com/hook", "events": ["trade.created"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("secret", response.data)
        self.assertEqual(Webhook.objects.count(), 1)

    def test_docs_sdk_analytics_and_sandbox(self):
        for url in ["/api/developer/docs/", "/api/developer/sdk/", "/api/developer/analytics/", "/api/developer/sandbox/"]:
            self.assertEqual(self.client.get(url).status_code, 200)
