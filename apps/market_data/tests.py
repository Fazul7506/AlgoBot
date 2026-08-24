from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount
from .models import MarketSymbol, Tick


class BrokerTickApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="market-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC123", status="active", is_preferred=True)
        MarketSymbol.objects.create(symbol="TEST", display_name="Test", market="Derived Indices", is_active=True, is_tradable=True)
        self.client.force_authenticate(self.user)

    def test_broker_tick_accepts_get(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.get("/api/market/ticks/broker/?symbol=TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["broker"], "Deriv")
        self.assertEqual(response.json()["account_id"], "VRTC123")
        self.assertFalse(response.json()["stale"])

    def test_broker_tick_accepts_post(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_broker_quote_is_idempotent(self):
        quote = {"symbol": "TEST", "quote": 100.25, "bid": 100.20, "ask": 100.30, "epoch": 1787560349, "volume": 0}
        with patch("apps.market_data.api.fetch_tick", return_value=quote):
            first = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
            second = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Tick.objects.filter(symbol__symbol="TEST", epoch=1787560349, quote="100.25000000").count(), 1)

    def test_transient_broker_failure_uses_last_known_quote(self):
        quote = {"symbol": "TEST", "quote": 101.25, "bid": 101.20, "ask": 101.30, "epoch": 1787560350, "volume": 0}
        with patch("apps.market_data.api.fetch_tick", return_value=quote):
            seed = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(seed.status_code, 200)
        with patch("apps.market_data.api.fetch_tick", side_effect=RuntimeError("broker timeout")):
            response = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["source"], "last_known_broker_quote")
        self.assertEqual(response.json()["quote"], "101.25000000")

    def test_broker_tick_requires_a_symbol(self):
        response = self.client.get("/api/market/ticks/broker/")
        self.assertEqual(response.status_code, 400)
