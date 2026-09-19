from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.analysis import views
from apps.market_data.models import Candle, MarketSymbol


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


    @patch.object(views, "fetch_contracts_for")
    def test_analysis_contracts_returns_deriv_capabilities(self, fetch_contracts):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
        )
        fetch_contracts.return_value = {
            "symbol": "R_100",
            "source": "deriv_public_websocket",
            "available": [{"underlying_symbol": "R_100", "contract_type": "MULTUP", "contract_category": "multiplier", "market": "synthetic_index", "submarket": "volatility", "exchange_name": "DERIV", "expiry_type": "intraday", "sentiment": "up", "barriers": 0}],
            "available_contract_types": ["MULTUP"],
            "available_contract_families": ["multiplier"],
            "expiry_types": ["intraday"],
            "sentiments": ["up"],
        }
        response = self.client.get(reverse("analysis-contracts"), {"symbol": market.symbol})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capabilities"]["available_contract_types"], ["MULTUP"])
        fetch_contracts.assert_called_once_with("R_100")

    def test_analysis_market_endpoint_is_user_authenticated(self):
        response = self.client.get(reverse("analysis-markets"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["markets"], [])
