from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.market_data.models import MarketSymbol


class BrokerNativeCatalogueFallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="catalogue-fallback-user", password="test-pass"
        )
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active", supports_live=True
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-CATALOGUE",
            status="active",
            credentials={"account_type": "demo"},
        )
        BrokerConnection.objects.create(
            broker=self.broker, broker_account=self.account, status="connected"
        )
        MarketSymbol.objects.create(
            broker="deriv",
            symbol="TEST",
            display_name="Test Instrument",
            market="Derived Indices",
            is_active=True,
            is_tradable=True,
        )
        self.client.force_authenticate(self.user)

    @patch(
        "apps.market_data.broker_native._public_deriv",
        side_effect=RuntimeError("provider unavailable"),
    )
    def test_catalogue_serves_last_known_database_symbols_when_deriv_is_unavailable(self, _request):
        response = self.client.get("/api/market/catalogue/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["source"], "cached_broker_catalogue")
        self.assertEqual(response.json()["account_id"], "VRTC-CATALOGUE")
        self.assertEqual(response.json()["symbols"][0]["symbol"], "TEST")
