from django.test import SimpleTestCase

from .calculator import IndicatorCalculator


class IndicatorCalculatorTests(SimpleTestCase):
    def setUp(self):
        self.calculator = IndicatorCalculator()
        self.candles = [
            {
                "open": i,
                "high": i + 1,
                "low": i - 1,
                "close": i,
                "volume": 100,
            }
            for i in range(1, 61)
        ]

    def test_indicators_report_insufficient_data_instead_of_fabricating(self):
        short = self.candles[:10]
        self.assertIsNone(self.calculator.sma(short, 20))
        self.assertIsNone(self.calculator.ema(short, 20))
        self.assertIsNone(self.calculator.rsi(short, 14))
        self.assertIsNone(self.calculator.atr(short, 14))
        self.assertIsNone(self.calculator.macd(short))

    def test_rsi_is_bounded_and_directionally_correct(self):
        rising = self.calculator.rsi(self.candles, 14)
        falling = self.calculator.rsi(
            [{**row, "close": 61 - row["close"]} for row in self.candles], 14
        )
        self.assertGreaterEqual(rising, 0)
        self.assertLessEqual(rising, 100)
        self.assertGreater(rising, falling)

    def test_ema_uses_period_seed(self):
        self.assertEqual(self.calculator.ema(self.candles[:10], 20), None)
        value = self.calculator.ema(self.candles, 20)
        self.assertIsNotNone(value)
        self.assertGreater(value, 40)

    def test_macd_has_real_signal_and_histogram(self):
        result = self.calculator.macd(self.candles)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(
            result["histogram"],
            result["macd"] - result["signal"],
            places=12,
        )

    def test_bollinger_requires_full_window(self):
        self.assertIsNone(self.calculator.bollinger_bands(self.candles[:19], 20))
        bands = self.calculator.bollinger_bands(self.candles, 20)
        self.assertLess(bands["lower"], bands["middle"])
        self.assertLess(bands["middle"], bands["upper"])
