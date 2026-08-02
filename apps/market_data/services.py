from decimal import Decimal
from django.db.models import Avg, Max, Min, Count
from django.utils import timezone
from .cache import MarketCacheService
from .constants import TIMEFRAMES, EVENT_TICK_RECEIVED, EVENT_NEW_CANDLE, EVENT_SUBSCRIPTION_ADDED, EVENT_SUBSCRIPTION_REMOVED
from .models import Candle, MarketSnapshot, MarketStatistics, MarketSymbol, Subscription, Tick
from .validators import ValidationService
from .websocket import event_bus

class SymbolService:
    def symbols(self): return MarketSymbol.objects.all()
    def symbol(self, symbol): return MarketSymbol.objects.get(symbol=symbol)
    def search(self, q): return MarketSymbol.objects.filter(symbol__icontains=q) | MarketSymbol.objects.filter(display_name__icontains=q)
    def active(self): return MarketSymbol.objects.filter(is_active=True)
    def inactive(self): return MarketSymbol.objects.filter(is_active=False)
    def favorite(self, user=None): return self.active()
    def market(self, market): return MarketSymbol.objects.filter(market=market)
    def submarket(self, submarket): return MarketSymbol.objects.filter(sub_market=submarket)

class CandleService:
    def bucket_epoch(self, epoch, seconds): return epoch if seconds == 0 else epoch - (epoch % seconds)
    def update_from_tick(self, tick):
        made=[]
        for timeframe, seconds in TIMEFRAMES.items():
            epoch = self.bucket_epoch(tick.epoch, seconds)
            candle, created = Candle.objects.get_or_create(symbol=tick.symbol, timeframe=timeframe, epoch=epoch, defaults={"open": tick.quote, "high": tick.quote, "low": tick.quote, "close": tick.quote, "volume": tick.volume})
            if not created:
                candle.high=max(candle.high,tick.quote); candle.low=min(candle.low,tick.quote); candle.close=tick.quote; candle.volume += tick.volume; candle.save(update_fields=["high","low","close","volume"])
            MarketCacheService().set_latest_candle(tick.symbol.symbol, timeframe, self.serialize(candle)); event_bus.publish(EVENT_NEW_CANDLE, self.serialize(candle)); made.append(candle)
        return made
    def serialize(self,c): return {"symbol": c.symbol.symbol, "timeframe": c.timeframe, "open": str(c.open), "high": str(c.high), "low": str(c.low), "close": str(c.close), "volume": str(c.volume), "epoch": c.epoch}

class TickService:
    def ingest(self, data):
        clean = ValidationService().validate_tick(data); spread = clean["ask"] - clean["bid"]
        tick = Tick.objects.create(**clean, spread=spread, received_at=timezone.now())
        payload = self.serialize(tick); MarketCacheService().set_latest_tick(tick.symbol.symbol, payload)
        self.update_snapshot(tick); event_bus.publish(EVENT_TICK_RECEIVED, payload); CandleService().update_from_tick(tick)
        return tick
    def update_snapshot(self,tick):
        defaults={"last_price":tick.quote,"bid":tick.bid,"ask":tick.ask,"spread":tick.spread,"timestamp":timezone.now()}
        snap,_=MarketSnapshot.objects.get_or_create(symbol=tick.symbol, defaults={**defaults,"high":tick.quote,"low":tick.quote,"volume":tick.volume})
        if snap.pk:
            snap.last_price=tick.quote; snap.bid=tick.bid; snap.ask=tick.ask; snap.spread=tick.spread; snap.high=max(snap.high,tick.quote); snap.low=min(snap.low,tick.quote); snap.volume += tick.volume; snap.timestamp=timezone.now(); snap.save()
        MarketCacheService().set_snapshot(tick.symbol.symbol, {"last_price": str(snap.last_price), "spread": str(snap.spread)})
    def serialize(self,t): return {"symbol":t.symbol.symbol,"bid":str(t.bid),"ask":str(t.ask),"quote":str(t.quote),"spread":str(t.spread),"epoch":t.epoch,"volume":str(t.volume)}

class HistoricalDataService:
    def tick_history(self, symbol, limit=1000): return Tick.objects.filter(symbol__symbol=symbol).order_by("-epoch")[:limit]
    def candle_history(self, symbol, timeframe="1m", limit=1000): return Candle.objects.filter(symbol__symbol=symbol,timeframe=timeframe).order_by("-epoch")[:limit]
    def export(self, queryset): return list(queryset.values())
    def compress(self): return None
    def incremental_updates(self, symbol, since_epoch): return Tick.objects.filter(symbol__symbol=symbol, epoch__gt=since_epoch)

class MarketStatisticsService:
    def calculate(self, symbol):
        sym = MarketSymbol.objects.get(symbol=symbol) if isinstance(symbol,str) else symbol
        agg=Tick.objects.filter(symbol=sym).aggregate(avg_spread=Avg("spread"), high=Max("quote"), low=Min("quote"), high_vol=Max("volume"), count=Count("id"), avg_vol=Avg("volume"))
        return MarketStatistics.objects.create(symbol=sym, average_spread=agg["avg_spread"] or 0, highest_price=agg["high"] or 0, lowest_price=agg["low"] or 0, highest_volume=agg["high_vol"] or 0, tick_count=agg["count"] or 0, average_volume=agg["avg_vol"] or 0)

class SubscriptionService:
    def add(self,user,symbol,timeframe="tick"):
        sub,_=Subscription.objects.get_or_create(user=user,symbol=MarketSymbol.objects.get(symbol=symbol),timeframe=timeframe,defaults={"status":"active"}); event_bus.publish(EVENT_SUBSCRIPTION_ADDED,{"symbol":symbol,"timeframe":timeframe}); return sub
    def remove(self,user,symbol,timeframe="tick"):
        Subscription.objects.filter(user=user,symbol__symbol=symbol,timeframe=timeframe).update(status="cancelled"); event_bus.publish(EVENT_SUBSCRIPTION_REMOVED,{"symbol":symbol,"timeframe":timeframe})

class MarketDataService:
    tick_service=TickService(); candle_service=CandleService(); symbols=SymbolService(); history=HistoricalDataService(); stats=MarketStatisticsService(); subscriptions=SubscriptionService()
