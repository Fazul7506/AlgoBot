from django.test import TestCase
from apps.indicators.engine import IndicatorEngine
from apps.indicators.cache import IndicatorCacheService

class IndicatorEngineTests(TestCase):
    def candles(self): return [{'open':i,'high':i+1,'low':i-1,'close':i,'volume':100+i} for i in range(1,40)]
    def test_indicator_engine_calculates_and_caches_rsi(self):
        value=IndicatorEngine().calculate('R_100','1m',self.candles(),'RSI',persist=False)
        self.assertIsNotNone(value)
        self.assertEqual(IndicatorCacheService().get_latest('R_100','1m','RSI'), value)
    def test_multi_timeframe(self):
        result=IndicatorEngine().multi_timeframe('R_100', {'1m':self.candles(),'5m':self.candles()}, ['SMA','EMA'])
        self.assertIn('1m', result); self.assertIn('SMA', result['5m'])
