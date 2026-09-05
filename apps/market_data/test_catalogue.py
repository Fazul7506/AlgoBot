from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from .models import MarketSymbol


class BrokerCatalogueApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="catalogue-test", password="test-pass"
        )
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active", supports_live=True
        )
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="VRTC-CATALOGUE", status="active"
        )
        BrokerConnection.objects.create(
            broker=self.broker, broker_account=self.account, status="connected"
        )

    def tearDown(self):
        cache.clear()

    def test_public_catalogue_does_not_require_account_authentication(self):
        payload = {
            "active_symbols": [
                {
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Volatility 100 Index",
                    "market": "synthetic_index",
                    "submarket": "random_index",
                    "exchange_is_open": True,
                    "is_trading_suspended": False,
                    "pip_size": 2,
                }
            ]
        }
        with patch("apps.market_data.broker_native._request", return_value=payload):
            response = self.client.get("/api/market/broker-catalogue/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "public_broker_catalogue")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["symbols"][0]["symbol"], "R_100")
        self.assertTrue(MarketSymbol.objects.filter(symbol="R_100", broker="deriv").exists())

    def test_connected_account_is_reported_when_present(self):
        self.client.force_authenticate(self.user)
        payload = {
            "active_symbols": [
                {
                    "underlying_symbol": "EURUSD",
                    "underlying_symbol_name": "EUR/USD",
                    "market": "forex",
                    "exchange_is_open": True,
                    "is_trading_suspended": False,
                    "pip_size": 5,
                }
            ]
        }
        with patch("apps.market_data.broker_native._request", return_value=payload):
            response = self.client.get("/api/market/broker-catalogue/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "connected_broker_catalogue")
        self.assertEqual(body["account_id"], "VRTC-CATALOGUE")

    def test_closed_market_remains_in_catalogue_but_not_tradable(self):
        payload = {
            "active_symbols": [
                {
                    "underlying_symbol": "CLOSED",
                    "underlying_symbol_name": "Closed Market",
                    "market": "forex",
                    "exchange_is_open": False,
                    "is_trading_suspended": False,
                }
            ]
        }
        with patch("apps.market_data.broker_native._request", return_value=payload):
            response = self.client.get("/api/market/broker-catalogue/")

        self.assertEqual(response.status_code, 200)
        symbol = response.json()["symbols"][0]
        self.assertTrue(symbol["is_active"])
        self.assertFalse(symbol["is_tradable"])

    def test_catalogue_uses_last_known_database_data_when_broker_is_down(self):
        MarketSymbol.objects.create(
            symbol="R_50",
            broker="deriv",
            display_name="Volatility 50 Index",
            market="Derived Indices",
            is_active=True,
            is_tradable=True,
        )
        with patch(
            "apps.market_data.broker_native._request",
            side_effect=RuntimeError("provider unavailable"),
        ):
            response = self.client.get("/api/market/broker-catalogue/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "stale")
        self.assertTrue(body["stale"])
        self.assertEqual(body["symbols"][0]["symbol"], "R_50")

    def test_catalogue_returns_controlled_503_without_live_or_cached_data(self):
        with patch(
            "apps.market_data.broker_native._request",
            side_effect=RuntimeError("provider unavailable"),
        ):
            response = self.client.get("/api/market/broker-catalogue/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BROKER_CATALOGUE_UNAVAILABLE")
