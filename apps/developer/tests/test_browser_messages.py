from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.developer.models import APIKey, Webhook
from apps.developer.services import APIKeyService


class DeveloperBrowserMessagesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="browser-dev", password="pass12345")
        self.client.login(username="browser-dev", password="pass12345")

    def test_create_key_uses_django_message_and_one_time_session_reveal(self):
        response = self.client.post(
            "/api/developer/browser/keys/create/",
            {"name": "Browser production", "permissions": ["read", "trading"]},
        )
        self.assertRedirects(response, "/developer/", fetch_redirect_response=False)
        self.assertEqual(APIKey.objects.filter(user=self.user).count(), 1)
        self.assertTrue(any("API key created successfully" in str(message) for message in response.wsgi_request._messages))
        secret = self.client.session.get("developer_one_time_secret")
        self.assertEqual(secret["kind"], "api_key")
        self.assertTrue(secret["secret"])
        self.assertEqual(secret["key"], APIKey.objects.get(user=self.user).key)

    def test_delete_key_is_same_origin_form_action(self):
        key, _ = APIKeyService().create(self.user, "delete-me", ["read"])
        response = self.client.post(f"/api/developer/browser/keys/{key.id}/delete/")
        self.assertRedirects(response, "/developer/", fetch_redirect_response=False)
        self.assertFalse(APIKey.objects.filter(pk=key.id).exists())

    def test_create_webhook_uses_django_message_and_session_secret(self):
        response = self.client.post(
            "/api/developer/browser/webhooks/create/",
            {"url": "https://example.com/webhook", "events": ["order.created"]},
        )
        self.assertRedirects(response, "/developer/", fetch_redirect_response=False)
        self.assertEqual(Webhook.objects.filter(user=self.user).count(), 1)
        self.assertTrue(any("Webhook created successfully" in str(message) for message in response.wsgi_request._messages))
        secret = self.client.session.get("developer_one_time_secret")
        self.assertEqual(secret["kind"], "webhook")
        self.assertTrue(secret["secret"])
