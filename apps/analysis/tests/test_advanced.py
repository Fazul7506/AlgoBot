from django.test import SimpleTestCase

from apps.analysis.advanced import analyze_candles


class AdvancedAnalysisTests(SimpleTestCase):
    def candles(self, n=260):
        return [
            {"epoch": i, "open": 100 + i * 0.1, "high": 100.4 + i * 0.1, "low": 99.8 + i * 0.1, "close": 100.2 + i * 0.1, "volume": 1}
            for i in range(n)
        ]

    def test_analysis_returns_core_signal_and_levels(self):
        result = analyze_candles(self.candles(), "R_100", "M1")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candles"], 260)
        self.assertIn(result["signal"], {"Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"})
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertLess(result["levels"]["support"], result["levels"]["resistance"])
        self.assertIsNotNone(result["indicators"]["sma200"])

    def test_empty_data_is_explicit(self):
        result = analyze_candles([], "R_100", "M1")
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["candles"], 0)
