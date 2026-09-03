from django.test import SimpleTestCase

from apps.analysis.advanced import analyze_candles


class AdvancedAnalysisTests(SimpleTestCase):
    def candles(self, n=320):
        rows = []
        for i in range(n):
            base = 100 + i * 0.08
            # Deliberate impulses and pullbacks exercise structure/SMC detectors.
            if 90 <= i < 110:
                base += (i - 90) * 0.15
            if 180 <= i < 200:
                base -= (i - 180) * 0.12
            rows.append({
                "epoch": i,
                "open": base,
                "high": base + 0.5,
                "low": base - 0.35,
                "close": base + 0.25,
                "volume": 1,
            })
        return rows

    def test_analysis_returns_core_signal_and_levels(self):
        result = analyze_candles(self.candles(), "R_100", "M1")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candles"], 320)
        self.assertIn(result["signal"], {"Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"})
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertLess(result["levels"]["support"], result["levels"]["resistance"])
        self.assertIsNotNone(result["indicators"]["sma200"])

    def test_advanced_tools_are_returned(self):
        result = analyze_candles(self.candles(), "R_100", "M1")
        for key in (
            "market_structure",
            "events",
            "fair_value_gaps",
            "liquidity_sweeps",
            "supply_demand",
            "candlestick_patterns",
            "fibonacci",
            "volatility_regime",
        ):
            self.assertIn(key, result)
        self.assertIn(result["volatility_regime"], {"normal", "expanding", "contracting", "unknown"})
        self.assertIn("labels", result["market_structure"])

    def test_empty_data_is_explicit(self):
        result = analyze_candles([], "R_100", "M1")
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["candles"], 0)
