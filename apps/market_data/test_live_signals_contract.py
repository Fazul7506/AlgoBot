from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount
from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal

from .models import MarketSnapshot, MarketSymbol


class LiveSignalsContractTests(TestCase):
    def setUp(self):
        self.client = self.client_class()
        self.user = get_user_model().objects.create_user(username="signals-contract", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        self.account = BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC-SIGNALS", status="active", token_status="active")
        self.assertTrue(self.client.login(username="signals-contract", password="test-pass"))
        self.market = MarketSymbol.objects.create(symbol="R_100", display_name="Volatility 100", market="Derived Indices", broker="deriv", is_active=True, is_tradable=True)
        self.strategy = Strategy.objects.create(name="Live Test", slug="live-test", category="Trend Following", version="1", enabled=True)
        self.config = StrategyConfiguration.objects.create(strategy=self.strategy, user=self.user, broker_account=self.account, symbol="R_100", timeframe="M1", enabled=True)

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_live_signal_uses_public_broker_quote_and_matching_baseline(self, live_ticks):
        StrategySignal.objects.create(strategy=self.strategy, configuration=self.config, symbol="R_100", signal="BUY", confidence=80, entry_price="100.00000", timestamp=timezone.now())
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 25.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["live_data_available_count"], 1)
        self.assertEqual(payload["data"][0]["live"]["price"], 101.0)
        self.assertEqual(payload["data"][0]["baseline_direction"], "BUY")
        self.assertEqual(payload["feed_latency_ms"], 25.0)

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_fresh_persisted_deriv_stream_quote_is_preferred(self, live_ticks):
        MarketSnapshot.objects.create(
            symbol=self.market,
            last_price="101.25000",
            bid="101.24000",
            ask="101.26000",
            timestamp=timezone.now(),
        )
        StrategySignal.objects.create(
            strategy=self.strategy,
            configuration=self.config,
            symbol="R_100",
            signal="BUY",
            confidence=80,
            entry_price="100.00000",
            timestamp=timezone.now(),
        )
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["live"]["price"], 101.25)
        self.assertEqual(row["live"]["source"], "deriv_public_stream")
        live_ticks.assert_not_called()

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_missing_baseline_never_becomes_actionable(self, live_ticks):
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 12.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["status"], "WAITING_FOR_ANALYSIS")
        self.assertFalse(row["execution_ready"])
        self.assertEqual(row["confidence"], 0)

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_stale_analysis_cannot_be_trading_ready(self, live_ticks):
        StrategySignal.objects.create(strategy=self.strategy, configuration=self.config, symbol="R_100", signal="BUY", confidence=99, entry_price="100.00000", timestamp=timezone.now() - timedelta(hours=1))
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 15.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["status"], "ANALYSIS_STALE")
        self.assertFalse(row["execution_ready"])
