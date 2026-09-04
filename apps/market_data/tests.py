from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount
from .models import Candle, MarketSymbol, Tick


class BrokerTickApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="market-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC123", status="active")
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


class DataCenterQualityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="data-center-test", password="test-pass")
        self.client.force_authenticate(self.user)
        self.symbol = MarketSymbol.objects.create(symbol="DC_TEST", display_name="Data Center Test", market="Derived Indices", is_active=True, is_tradable=True)
        self.empty = MarketSymbol.objects.create(symbol="DC_EMPTY", display_name="Empty Symbol", market="Forex", is_active=True, is_tradable=False)

    def test_quality_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/data-center/quality/")
        self.assertEqual(response.status_code, 401)

    def test_quality_reports_tick_and_candle_coverage(self):
        Tick.objects.create(symbol=self.symbol, quote="100.5", epoch=100)
        Candle.objects.create(symbol=self.symbol, timeframe="1m", open="100", high="101", low="99", close="100.5", epoch=100)
        response = self.client.get("/api/data-center/quality/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["active_symbols"], 2)
        row = next(item for item in payload["symbols"] if item["symbol"] == "DC_TEST")
        self.assertEqual(row["tick_count"], 1)
        self.assertEqual(row["candle_count"], 1)
        self.assertEqual(row["candle_timeframes"], ["1m"])
        self.assertEqual(row["status"], "healthy")

    def test_quality_marks_old_received_ticks_stale(self):
        Tick.objects.create(symbol=self.symbol, quote="100.5", epoch=100, received_at=timezone.now() - timedelta(minutes=10))
        response = self.client.get("/api/data-center/quality/")
        row = next(item for item in response.json()["symbols"] if item["symbol"] == "DC_TEST")
        self.assertEqual(row["status"], "stale")
        self.assertGreaterEqual(response.json()["summary"]["stale_ticks"], 1)

    def test_quality_marks_empty_symbol_no_data(self):
        response = self.client.get("/api/data-center/quality/")
        row = next(item for item in response.json()["symbols"] if item["symbol"] == "DC_EMPTY")
        self.assertEqual(row["status"], "no_data")
