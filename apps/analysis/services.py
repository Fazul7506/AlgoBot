from .trend import TrendAnalysisService
from .volatility import VolatilityService
from .support_resistance import SupportResistanceService
from .patterns import PatternRecognitionService
class AnalysisService:
    def __init__(self): self.trend=TrendAnalysisService(); self.volatility=VolatilityService(); self.support_resistance=SupportResistanceService(); self.patterns=PatternRecognitionService()
    def analyze(self,symbol,timeframe,candles): return {'trend':self.trend.analyze(symbol,timeframe,candles),'volatility':self.volatility.analyze(symbol,timeframe,candles),'support_resistance':self.support_resistance.detect(symbol,timeframe,candles),'patterns':self.patterns.detect(symbol,timeframe,candles)}
