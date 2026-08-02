import json
from django.core.cache import cache

class MarketCacheService:
    prefix = "market_data"
    def key(self, *parts): return ":".join([self.prefix, *map(str, parts)])
    def set_latest_tick(self, symbol, data): cache.set(self.key("tick", symbol), data, 300)
    def latest_tick(self, symbol): return cache.get(self.key("tick", symbol))
    def set_latest_candle(self, symbol, timeframe, data): cache.set(self.key("candle", symbol, timeframe), data, 3600)
    def latest_candle(self, symbol, timeframe): return cache.get(self.key("candle", symbol, timeframe))
    def set_snapshot(self, symbol, data): cache.set(self.key("snapshot", symbol), data, 300)
    def snapshot(self, symbol): return cache.get(self.key("snapshot", symbol))
    def set_history(self, name, data, ttl=60): cache.set(self.key("history", name), data, ttl)
    def history(self, name): return cache.get(self.key("history", name))
