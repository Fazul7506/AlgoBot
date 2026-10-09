from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal

from .models import MarketSnapshot, MarketSymbol


class LiveSignalsContractTests(TestCase):
    def setUp(self):
        self.client = self.client_class()
        self.user = get_user_model().objects.create_user(username="signals-contract", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-SIGNALS",
            status="active",
            token_status="active",
            credentials={"account_type": "demo"},
            balance="1000.00",
            margin="0.00",
            free_margin="1000.00",
            last_synced_at=timezone.now(),
        )
        self.account.set_access_token("test-access-token")
        self.account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
            connected_at=timezone.now(),
        )
        self.assertTrue(self.client.login(username="signals-contract", password="test-pass"))
        self.market = MarketSymbol.objects.create(symbol="R_100", display_name="Volatility 100", market="Derived Indices", broker="deriv", is_active=True, is_tradable=True)
        self.strategy = Strategy.objects.create(name="Live Test", slug="live-test", category="Trend Following", version="1", enabled=True)
        self.config = StrategyConfiguration.objects.create(strategy=self.strategy, user=self.user, broker_account=self.account, symbol="R_100", timeframe="M1", enabled=True, is_active=True)

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
        self.assertIsInstance(payload["feed_latency_ms"], (int, float))
        self.assertGreaterEqual(payload["feed_latency_ms"], 0)

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_fresh_persisted_deriv_stream_quote_is_preferred(self, live_ticks):
        MarketSnapshot.objects.create(symbol=self.market, last_price="101.25000", bid="101.24000", ask="101.26000", timestamp=timezone.now())
        StrategySignal.objects.create(strategy=self.strategy, configuration=self.config, symbol="R_100", signal="BUY", confidence=80, entry_price="100.00000", timestamp=timezone.now())
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
        self.assertIsNone(row["confidence"])

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_stale_analysis_cannot_be_trading_ready(self, live_ticks):
        StrategySignal.objects.create(strategy=self.strategy, configuration=self.config, symbol="R_100", signal="BUY", confidence=99, entry_price="100.00000", timestamp=timezone.now() - timedelta(hours=1))
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 15.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["status"], "ANALYSIS_STALE")
        self.assertFalse(row["execution_ready"])

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_inactive_strategy_signal_is_not_used_as_live_baseline(self, live_ticks):
        self.config.is_active = True
        self.config.enabled = True
        self.config.save(update_fields=["is_active", "enabled"])

        inactive_strategy = Strategy.objects.create(
            name="Inactive Test",
            slug="inactive-test",
            category="Trend Following",
            version="1",
            enabled=True,
        )
        inactive_config = StrategyConfiguration.objects.create(
            strategy=inactive_strategy,
            user=self.user,
            broker_account=self.account,
            symbol="R_100",
            timeframe="M1",
            enabled=True,
            is_active=False,
        )
        StrategySignal.objects.create(
            strategy=inactive_strategy,
            configuration=inactive_config,
            symbol="R_100",
            signal="SELL",
            confidence=99,
            entry_price="102.00000",
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
        live_ticks.return_value = ({
            "R_100": {
                "symbol": "R_100",
                "quote": 101.0,
                "epoch": int(timezone.now().timestamp()),
            }
        }, 12.0)

        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["baseline_direction"], "BUY")
        self.assertEqual(row["analysis_signal_id"], StrategySignal.objects.get(configuration=self.config).id)


    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_signal_exposes_canonical_lifecycle_and_provenance(self, live_ticks):
        StrategySignal.objects.create(
            strategy=self.strategy,
            configuration=self.config,
            symbol="R_100",
            signal="BUY",
            confidence=80,
            entry_price="100.00000",
            timestamp=timezone.now(),
        )
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 10.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = payload["data"][0]
        self.assertEqual(payload["research_state"], "READY")
        self.assertEqual(payload["broker_state"], "BROKER_CONNECTED")
        self.assertEqual(row["lifecycle"], "ACTIONABLE")
        self.assertTrue(row["signal_valid"])
        self.assertEqual(row["confidence_source"], "strategy_signal")
        self.assertEqual(row["provenance"]["execution"], "Not executed")

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_live_confirmation_conflict_invalidates_signal_without_rewriting_confidence(self, live_ticks):
        StrategySignal.objects.create(
            strategy=self.strategy,
            configuration=self.config,
            symbol="R_100",
            signal="BUY",
            confidence=91,
            entry_price="110.00000",
            timestamp=timezone.now(),
        )
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 10.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        row = response.json()["data"][0]
        self.assertEqual(row["lifecycle"], "INVALIDATED")
        self.assertEqual(row["status"], "LIVE_CONFIRMATION_FAILED")
        self.assertEqual(row["confidence"], 91.0)
        self.assertFalse(row["execution_ready"])

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_signal_is_blocked_when_account_risk_inputs_are_incomplete(self, live_ticks):
        self.account.last_synced_at = None
        self.account.save(update_fields=["last_synced_at"])
        StrategySignal.objects.create(
            strategy=self.strategy,
            configuration=self.config,
            symbol="R_100",
            signal="BUY",
            confidence=95,
            entry_price="100.00000",
            timestamp=timezone.now(),
        )
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": 101.0, "epoch": int(timezone.now().timestamp())}}, 10.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"][0]
        self.assertEqual(row["status"], "RISK_CONTEXT_INCOMPLETE")
        self.assertEqual(row["lifecycle"], "BLOCKED")
        self.assertFalse(row["execution_ready"])

    @patch("apps.market_data.signal_views._live_deriv_ticks")
    def test_non_finite_live_quote_is_not_returned_as_market_data(self, live_ticks):
        live_ticks.return_value = ({"R_100": {"symbol": "R_100", "quote": float("nan"), "epoch": int(timezone.now().timestamp())}}, 10.0)
        response = self.client.get("/api/strategy-signals/?symbol=R_100&timeframe=M1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "MARKET_DATA_UNAVAILABLE")
