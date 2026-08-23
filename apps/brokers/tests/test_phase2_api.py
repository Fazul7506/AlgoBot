from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.brokers.models import Broker, BrokerAccount


class BrokerAccountApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("owner", "owner@example.com", "pass")
        self.other = get_user_model().objects.create_user("other", "other@example.com", "pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv")
        self.account = BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC123")
        self.other_account = BrokerAccount.objects.create(user=self.other, broker=self.broker, account_id="VRTC456")
        self.client.force_authenticate(self.user)

    def test_accounts_are_owned_and_credentials_are_not_serialized(self):
        response = self.client.get(reverse("broker-accounts-detail", args=[self.other_account.pk]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("broker-accounts-detail", args=[self.account.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("credentials", response.data)

    @patch("apps.brokers.views.SynchronizationService.sync_account", new_callable=AsyncMock)
    def test_sync_returns_broker_sourced_account_data(self, sync):
        self.account.balance = "42.50"
        sync.return_value = (self.account, {"balance": "42.50", "currency": "USD"})
        response = self.client.post(reverse("broker-accounts-sync", args=[self.account.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "deriv_authorize")
        self.assertEqual(str(response.data["account"]["balance"]), "42.50000000")
