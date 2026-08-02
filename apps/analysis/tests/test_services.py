from django.test import SimpleTestCase
from apps.analysis.services import AnalysisService

class AnalysisServiceTests(SimpleTestCase):
    def candles(self): return [{'open':i,'high':i+1,'low':i-1,'close':i+(i%3)*.1,'volume':100+i} for i in range(1,40)]
    def test_full_analysis_payload(self):
        data=AnalysisService().analyze('R_100','1m',self.candles())
        self.assertIn('trend', data); self.assertIn('volatility', data); self.assertIn('patterns', data); self.assertIn('support_resistance', data)
    def test_support_resistance_levels(self):
        data=AnalysisService().support_resistance.detect('R_100','1m',self.candles())
        self.assertTrue(data['levels'])
