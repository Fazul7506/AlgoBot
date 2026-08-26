import unittest

from trading.ai.candlestick_features import FEATURE_NAMES, extract_candlestick_features, feature_vector


class CandlestickFeatureTests(unittest.TestCase):
    def _bars(self):
        bars=[]
        price=100.0
        for i in range(40):
            close=price + (0.15 if i % 3 else -0.05)
            bars.append({'open':price,'high':max(price,close)+0.25,'low':min(price,close)-0.25,'close':close,'volume':100+i})
            price=close
        return bars

    def test_contract_has_expected_features(self):
        bars=self._bars()
        features=extract_candlestick_features(bars)
        vector=feature_vector(bars)
        self.assertEqual(len(features), len(FEATURE_NAMES))
        self.assertEqual(len(vector), len(FEATURE_NAMES))
        self.assertTrue(all(isinstance(v, float) for v in vector))

    def test_inside_bar_is_detected(self):
        bars=self._bars()
        parent=bars[-2]
        bars[-1]={'open':parent['close']-0.02,'high':parent['high']-0.05,'low':parent['low']+0.05,'close':parent['close']+0.01,'volume':100}
        features=extract_candlestick_features(bars)
        self.assertEqual(features['inside_bar'], 1.0)

    def test_bullish_engulfing_is_detected(self):
        bars=self._bars()
        bars[-2]={'open':101.0,'high':101.2,'low':99.8,'close':100.0,'volume':100}
        bars[-1]={'open':99.7,'high':102.0,'low':99.5,'close':101.5,'volume':120}
        features=extract_candlestick_features(bars)
        self.assertEqual(features['bullish_engulfing'], 1.0)
