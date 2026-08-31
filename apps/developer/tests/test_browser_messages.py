from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.developer.models import APIKey, Webhook
from apps.developer.services import APIKeyService


class DeveloperBrowserMessagesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="browser-dev", password="pass12345")
        self.client.login(username="browser-dev", password="pass12345")

    def test_dashboard_is_server_rendered_without_developer_api_bootstrap(self):
        response = self.client.get("/developer/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Developer API")
        self.assertNotContains(response, "data-dev-keys")
        self.assertNotContains(response, "data-dev-webhooks")
        self.assertNotContains(response, "Backend returned an unexpected HTML response")

    def test_create_key_uses_django_message_and_one_time_session_reveal(self):
        response = self.client.post(
            "/api/developer/browser/keys/create/",
            {"name": "Browser production", "permissions": ["read", "trading"]},
        )
        self.assertRedirects(response, "/developer/")
        self.assertEqual(APIKey.objects.filter(user=self.user).count(), 1)

        dashboard = self.client.get("/developer/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Save this secret now")
        self.assertContains(dashboard, "Browser production")
        self.assertContains(dashboard, "API key created successfully")

        # Secret reveal is consumed after the redirect GET and is not replayed.
        second = self.client.get("/developer/")
        self.assertNotContains(second, "Save this secret now")

    def test_delete_key_is_same_origin_form_action(self):
        key, _ = APIKeyService().create(self.user, "delete-me", ["read"])
        response = self.client.post(f"/api/developer/browser/keys/{key.id}/delete/")
        self.assertRedirects(response, "/developer/")
        self.assertFalse(APIKey.objects.filter(pk=key.id).exists())

    def test_create_webhook_uses_django_message(self):
        response = self.client.post(
            "/api/developer/browser/webhooks/create/",
            {"url": "https://example.com/webhook", "events": ["order.created"]},
        )
        self.assertRedirects(response, "/developer/")
        self.assertEqual(Webhook.objects.filter(user=self.user).count(), 1)
        dashboard = self.client.get("/developer/")
        self.assertContains(dashboard, "Signing secret")
        self.assertContains(dashboard, "Webhook created successfully")
