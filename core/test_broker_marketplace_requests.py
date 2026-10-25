import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.brokers.models import BrokerIntegrationRequest


class BrokerMarketplaceRequestTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="marketplace-request-user",
            email="requester@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_marketplace_request_is_saved_for_integration_team(self):
        response = self.client.post(
            reverse("submit_broker_marketplace_request"),
            data=json.dumps({
                "provider_name": "Example Broker",
                "provider_website": "https://example.com",
                "use_case": "Support account authorization and market data.",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        saved = BrokerIntegrationRequest.objects.get(provider_name="Example Broker")
        self.assertEqual(saved.requested_by, self.user)
        self.assertEqual(saved.status, "pending")
        self.assertEqual(saved.provider_website, "https://example.com")
        self.assertIn("request_id", response.json())

    def test_marketplace_request_requires_provider_and_use_case(self):
        response = self.client.post(
            reverse("submit_broker_marketplace_request"),
            data=json.dumps({"provider_name": "Example Broker", "use_case": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BrokerIntegrationRequest.objects.count(), 0)

    def test_marketplace_request_rejects_invalid_website_scheme(self):
        response = self.client.post(
            reverse("submit_broker_marketplace_request"),
            data=json.dumps({
                "provider_name": "Example Broker",
                "provider_website": "javascript:alert(1)",
                "use_case": "Support account authorization.",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BrokerIntegrationRequest.objects.count(), 0)
