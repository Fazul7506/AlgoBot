from .engine import IndicatorEngine
from .repositories import IndicatorRepository
class IndicatorService:
    def __init__(self): self.engine=IndicatorEngine(); self.repository=IndicatorRepository()
    def calculate_indicators(self,symbol,timeframe,candles,indicators=None): return self.engine.calculate_all(symbol,timeframe,candles,indicators)
    def calculate_mtf(self,symbol,candles_by_timeframe,indicators=None): return self.engine.multi_timeframe(symbol,candles_by_timeframe,indicators)
    def latest(self,symbol,timeframe,indicator=None): return self.repository.latest(symbol,timeframe,indicator)
