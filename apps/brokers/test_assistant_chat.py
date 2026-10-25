import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import resolve, reverse


class BrokerIntegrationAssistantRouteTests(SimpleTestCase):
    def test_chat_endpoint_is_registered(self):
        url = reverse("broker_integration_assistant_chat")
        self.assertEqual(url, "/operations/broker-integrations/assistant/")
        match = resolve(url)
        self.assertEqual(match.url_name, "broker_integration_assistant_chat")


from unittest.mock import Mock, patch

from apps.brokers.workspace_views import _fetch_official_broker_documentation


class BrokerOfficialDocumentationResearchTests(SimpleTestCase):
    @patch("requests.get")
    def test_research_uses_fixed_official_source_and_extracts_readable_content(self, get):
        response = Mock()
        response.ok = True
        response.content = b"<html><script>secret()</script><main>REST API authentication endpoint request response details " * 4 + b"</main></html>"
        response.text = response.content.decode()
        response.url = "https://developer.oanda.com/rest-live-v20/introduction/"
        get.return_value = response

        docs = _fetch_official_broker_documentation("OANDA")

        self.assertIn("https://developer.oanda.com/rest-live-v20/introduction/", docs)
        self.assertIn("REST API authentication", docs)
        self.assertNotIn("secret()", docs)
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["timeout"], (4, 8))

    @patch("requests.get")
    def test_research_fails_closed_when_official_source_is_unavailable(self, get):
        get.side_effect = __import__("requests").RequestException("offline")
        self.assertEqual(_fetch_official_broker_documentation("OANDA"), "")

    @patch("requests.get")
    def test_unknown_provider_does_not_fetch_a_user_controlled_url(self, get):
        self.assertEqual(_fetch_official_broker_documentation("https://attacker.invalid"), "")
        get.assert_not_called()

    @patch("requests.get")
    def test_research_rejects_redirect_outside_official_host(self, get):
        response = Mock()
        response.ok = True
        response.content = b"API endpoint authentication authorization REST API documentation " * 4
        response.text = response.content.decode()
        response.url = "https://attacker.invalid/copied-docs"
        get.return_value = response
        self.assertEqual(_fetch_official_broker_documentation("OANDA"), "")



class BrokerAssistantAttachmentValidationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="broker-assistant-attachment-admin",
            password="test-only-password",
            is_staff=True,
        )
        self.client.force_login(self.admin)
        self.url = reverse("broker_integration_assistant_chat")

    def test_rejects_unsupported_attachment_type(self):
        response = self.client.post(
            self.url,
            data=json.dumps({
                "message": "OANDA",
                "attachments": [{"name": "payload.exe", "type": "application/octet-stream", "text": "not allowed"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unsupported format", response.json()["reply"])

    @patch("apps.brokers.workspace_views._fetch_official_broker_documentation", return_value="")
    def test_accepts_text_attachment_without_asking_for_a_documentation_form(self, fetch_docs):
        response = self.client.post(
            self.url,
            data=json.dumps({
                "message": "OANDA",
                "attachments": [{"name": "api-notes.md", "type": "text/markdown", "text": "Official API authentication and REST endpoint notes for this provider."}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attempted to retrieve its documentation automatically", response.json()["reply"])
        fetch_docs.assert_called_once_with("OANDA")
