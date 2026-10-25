from django.test import SimpleTestCase
from django.urls import resolve, reverse


class BrokerIntegrationAssistantRouteTests(SimpleTestCase):
    def test_chat_endpoint_is_registered(self):
        url = reverse("broker_integration_assistant_chat")
        self.assertEqual(url, "/operations/broker-integrations/assistant/")
        match = resolve(url)
        self.assertEqual(match.url_name, "broker_integration_assistant_chat")
