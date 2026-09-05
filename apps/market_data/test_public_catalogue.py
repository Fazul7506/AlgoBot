from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient


class PublicCatalogueCompatibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "active_symbols": [
                {
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Volatility 100 Index",
                    "market": "synthetic_index",
                    "submarket": "random_index",
                    "exchange_is_open": True,
                    "is_trading_suspended": False,
                },
                {
                    "underlying_symbol": "EURUSD",
                    "underlying_symbol_name": "EUR/USD",
                    "market": "forex",
                    "submarket": "major_pairs",
                    "exchange_is_open": True,
                    "is_trading_suspended": False,
                },
            ]
        }

    @patch("apps.market_data.broker_native._request")
    def test_markets_symbols_endpoint_is_live_broker_backed(self, request):
        request.return_value = self.payload
        response = self.client.get("/api/markets/symbols/?limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["symbol"] for row in response.json()}, {"R_100", "EURUSD"})

    @patch("apps.market_data.broker_native._request")
    def test_markets_endpoint_returns_broker_groups(self, request):
        request.return_value = self.payload
        response = self.client.get("/api/markets/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Forex", response.json()["markets"])
        self.assertIn("Volatility Indices", response.json()["markets"])
