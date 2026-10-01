from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.analysis import views
from apps.market_data.models import Candle, MarketSymbol
from apps.brokers.models import Broker, BrokerAccount
from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal


class AnalysisSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analytics-smoke", password="test-pass-123"
        )
        self.client.force_login(self.user)
        cache.clear()

    def test_analysis_markets_cache_is_reused(self):
        MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )
        with patch.object(
            views.MarketSymbol.objects,
            "filter",
            wraps=views.MarketSymbol.objects.filter,
        ) as query:
            first = views._analysis_markets()
            second = views._analysis_markets()
        self.assertEqual(first, second)
        self.assertEqual(query.call_count, 1)

    @patch.object(views, "fetch_contracts_for")
    def test_analysis_data_uses_persisted_candles_and_normalizes_aliases(self, fetch_contracts):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )
        for epoch, close in ((100, 100), (160, 101), (220, 102)):
            Candle.objects.create(
                symbol=market,
                timeframe="1m",
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1,
                epoch=epoch,
            )
        fetch_contracts.return_value = {
            "available_contract_types": ["MULTUP", "MULTDOWN"],
            "available_contract_families": ["multiplier"],
            "expiry_types": ["intraday"],
            "sentiments": ["up", "down"],
        }
        with patch.object(
            views,
            "analyze_candles",
            return_value={"status": "ok", "candles": 3, "signal": "NO_TRADE", "technical_signal": "Bullish", "technical_score": 70, "confidence": None, "structure": "Bullish structure", "volatility_regime": "normal", "factors": ["EMA 9/21 trend"]},
        ) as analyze:
            response = self.client.get(
                reverse("analysis-data"),
                {"symbol": market.symbol, "timeframe": "M1", "limit": 300},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(analyze.call_args.kwargs["timeframe"], "1m")
        self.assertEqual(response.json()["data_provenance"]["source"], "market_data.Candle")
        self.assertEqual(response.json()["data_provenance"]["candle_count"], 3)
        spec = response.json()["trade_spec"]
        self.assertEqual(spec["contract_type"], "MULTUP / MULTDOWN")
        self.assertEqual(spec["direction"], "HOLD")
        self.assertEqual(response.json()["ai"]["decision"], "AVOID")
        self.assertFalse(response.json()["execution_gate"]["sufficient_history"])
        self.assertTrue(spec["strategy"])
        self.assertTrue(spec["entry_condition"])
        self.assertEqual(response.json()["contract_capabilities"]["available_contract_families"], ["multiplier"])

        payload = response.json()
        self.assertIn(payload["research_state"], {"READY", "STALE"})
        self.assertIn("market_data", payload["analysis_layers"])
        self.assertIn("technical", payload["analysis_layers"])
        self.assertIn("strategy", payload["analysis_layers"])
        self.assertIn("ai", payload["analysis_layers"])
        self.assertIn(payload["confluence"]["state"], {"CONFIRMED", "CONDITIONAL"})
        self.assertTrue(payload["signal_validation"]["no_look_ahead"])
        self.assertTrue(payload["signal_validation"]["execution_separate"])

    def test_analysis_data_reports_missing_persisted_candles(self):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )
        response = self.client.get(
            reverse("analysis-data"),
            {"symbol": market.symbol, "timeframe": "1m", "limit": 300},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["source"], "market_data.Candle")


    @patch.object(views, "_authenticated_contract_capabilities")
    @patch.object(views.SynchronizationService, "sync_account", new_callable=AsyncMock)
    @patch.object(views, "get_active_account")
    def test_analysis_contracts_returns_authenticated_deriv_capabilities(self, get_active, sync_account, fetch_contracts):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )
        get_active.return_value = type(
            "Account",
            (),
            {
                "account_id": "CR123",
                "account_type": "demo",
                "currency": "USD",
                "credential_status": "ready",
                "token_status": "active",
                "broker": type("Broker", (), {"broker_type": "deriv"})(),
            },
        )()
        sync_account.return_value = (get_active.return_value, {})
        fetch_contracts.return_value = {
            "symbol": "R_100",
            "source": "deriv_authenticated_contracts_for",
            "available": [
                {
                    "underlying_symbol": "R_100",
                    "contract_type": "MULTUP",
                    "contract_category": "multiplier",
                    "market": "synthetic_index",
                    "submarket": "volatility",
                    "exchange_name": "DERIV",
                    "expiry_type": "intraday",
                    "sentiment": "up",
                    "barriers": 0,
                }
            ],
            "available_contract_types": ["MULTUP"],
            "available_contract_families": ["multiplier"],
            "market_types": ["synthetic_index"],
            "submarkets": ["volatility"],
            "expiry_types": ["intraday"],
            "sentiments": ["up"],
            "barriers": ["0"],
        }
        response = self.client.get(reverse("analysis-contracts"), {"symbol": market.symbol})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capabilities"]["available_contract_types"], ["MULTUP"])
        fetch_contracts.assert_called_once_with(get_active.return_value, "R_100")
        sync_account.assert_awaited_once_with(get_active.return_value)
        self.assertEqual(response.json()["account"]["credential_status"], "ready")
        self.assertEqual(response.json()["capabilities"]["market_types"], ["synthetic_index"])

    def test_analysis_market_endpoint_is_user_authenticated(self):
        response = self.client.get(reverse("analysis-markets"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["markets"], [])


class AnalysisArchitectureReconciliationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analysis-architecture", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active"
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="CR-ANALYSIS",
            status="active",
            credentials={"account_type": "demo"},
        )
        cache.clear()

    def test_latest_strategy_baseline_is_account_scoped_and_past_only(self):
        strategy = Strategy.objects.create(
            name="Canonical Strategy",
            slug="canonical-strategy",
            category="Trend Following",
        )
        config = StrategyConfiguration.objects.create(
            strategy=strategy,
            user=self.user,
            broker_account=self.account,
            symbol="R_100",
            timeframe="M1",
            enabled=True,
            is_active=True,
        )
        StrategySignal.objects.create(
            strategy=strategy,
            configuration=config,
            symbol="R_100",
            signal="BUY",
            confidence=81,
        )
        from apps.analysis.views import _latest_strategy_baseline
        baseline = _latest_strategy_baseline(
            type("Request", (), {"user": self.user})(),
            self.account,
            "R_100",
            "M1",
        )
        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.signal, "BUY")
        self.assertEqual(baseline.configuration.broker_account_id, self.account.id)

    @patch.object(views, "_authenticated_contract_capabilities")
    def test_analysis_prefers_authenticated_contract_capabilities_for_active_account(self, authenticated_caps):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
            broker="deriv",
        )
        for epoch, close in ((100, 100), (160, 101), (220, 102)):
            Candle.objects.create(
                symbol=market,
                timeframe="1m",
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1,
                epoch=epoch,
            )
        authenticated_caps.return_value = {
            "symbol": "R_100",
            "source": "deriv_authenticated_contracts_for",
            "available": [{"contract_type": "CALL", "contract_category": "rise_fall"}],
            "available_contract_types": ["CALL"],
            "available_contract_families": ["rise_fall"],
            "expiry_types": ["intraday"],
            "sentiments": ["up"],
        }
        response = self.client.get(
            reverse("analysis-data"),
            {"symbol": "R_100", "timeframe": "M1", "limit": 300, "refresh": "0"},
        )
        self.assertEqual(response.status_code, 200)
        authenticated_caps.assert_called_once_with(self.account, "R_100")
        self.assertEqual(
            response.json()["contract_capabilities"]["source"],
            "deriv_authenticated_contracts_for",
        )
