from django.core.cache import cache
class IndicatorCacheService:
    timeout=3600
    def key(self,*parts): return 'ta:' + ':'.join(map(str,parts))
    def set_latest(self,symbol,timeframe,indicator,value): return cache.set(self.key('latest',symbol,timeframe,indicator), value, self.timeout)
    def get_latest(self,symbol,timeframe,indicator): return cache.get(self.key('latest',symbol,timeframe,indicator))
    def set_analysis(self,kind,symbol,timeframe,value): return cache.set(self.key(kind,symbol,timeframe), value, self.timeout)
    def get_analysis(self,kind,symbol,timeframe): return cache.get(self.key(kind,symbol,timeframe))
