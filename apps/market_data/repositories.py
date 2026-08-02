from .cache import MarketCacheService
from .models import Candle, MarketSnapshot, MarketSymbol, Tick

class MarketRepository:
    @staticmethod
    def latest_tick(symbol):
        cached = MarketCacheService().latest_tick(symbol)
        return cached or Tick.objects.filter(symbol__symbol=symbol).order_by("-epoch").first()
    @staticmethod
    def latest_candle(symbol, timeframe="1m"):
        cached = MarketCacheService().latest_candle(symbol, timeframe)
        return cached or Candle.objects.filter(symbol__symbol=symbol, timeframe=timeframe).order_by("-epoch").first()
    @staticmethod
    def history(symbol, timeframe=None, limit=500):
        qs = Candle.objects.filter(symbol__symbol=symbol, timeframe=timeframe).order_by("-epoch") if timeframe else Tick.objects.filter(symbol__symbol=symbol).order_by("-epoch")
        return qs[:limit]
    @staticmethod
    def snapshot(symbol):
        return MarketCacheService().snapshot(symbol) or MarketSnapshot.objects.filter(symbol__symbol=symbol).first()
    @staticmethod
    def symbols(): return MarketSymbol.objects.filter(is_active=True)
