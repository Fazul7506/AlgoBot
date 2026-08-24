from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.brokers.models import Broker, BrokerAccount


class BrokerConnectionContractTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("connection-owner", "connection@example.com", "pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="BROKER-ACCOUNT",
            status="active",
            credentials={},
        )
        self.client.force_authenticate(self.user)

    def test_unconfirmed_account_type_is_unknown(self):
        response = self.client.get(reverse("broker-accounts-detail", args=[self.account.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account_type"], "unknown")
        self.assertNotIn("credentials", response.data)

    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_switch_rejects_unconfirmed_account_type(self):
        response = self.client.post(
            reverse("broker-accounts-select", args=[self.account.pk]),
            {"account_type": "demo"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("confirmed", response.data["detail"])
        self.assertFalse(self.account.is_preferred)
