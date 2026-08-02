import logging
from concurrent.futures import ThreadPoolExecutor
from .calculator import IndicatorCalculator
from .cache import IndicatorCacheService
from .constants import CORE_INDICATORS
from .repositories import IndicatorRepository
from .validators import validate_timeframe, validate_indicator_parameters
log=logging.getLogger(__name__)
class SignalEventPublisher:
    def publish(self,event_type,payload): log.info('%s %s', event_type, payload); return {'event':event_type,'payload':payload}
class IndicatorEngine:
    def __init__(self,calculator=None,cache=None,repository=None,publisher=None):
        self.calculator=calculator or IndicatorCalculator(); self.cache=cache or IndicatorCacheService(); self.repository=repository or IndicatorRepository(); self.publisher=publisher or SignalEventPublisher()
    def calculate(self,symbol,timeframe,candles,indicator_name,parameters=None,persist=True):
        validate_timeframe(timeframe); params=validate_indicator_parameters(parameters or {})
        value=self.calculator.generic(indicator_name,candles,**params)
        self.cache.set_latest(symbol,timeframe,indicator_name,value)
        if persist:
            indicator=self.repository.get_or_create_indicator(indicator_name, parameters=params)
            self.repository.save_value(symbol,timeframe,indicator,value,{'parameters':params,'source':'IndicatorEngine'})
        self.publisher.publish('IndicatorUpdated',{'symbol':symbol,'timeframe':timeframe,'indicator':indicator_name,'value':value})
        return value
    def calculate_all(self,symbol,timeframe,candles,indicators=None):
        names=indicators or CORE_INDICATORS
        with ThreadPoolExecutor(max_workers=min(8,len(names))) as pool:
            return dict(zip(names, pool.map(lambda n: self.calculate(symbol,timeframe,candles,n), names)))
    def multi_timeframe(self,symbol,candles_by_timeframe,indicators=None):
        return {tf:self.calculate_all(symbol,tf,candles,indicators) for tf,candles in candles_by_timeframe.items()}
