from decimal import Decimal
from django.db import IntegrityError, transaction
from django.db.models import Avg, Max, Min, Count, Q
from django.utils import timezone
from .cache import MarketCacheService
from .constants import TIMEFRAMES, EVENT_TICK_RECEIVED, EVENT_NEW_CANDLE, EVENT_SUBSCRIPTION_ADDED, EVENT_SUBSCRIPTION_REMOVED
from .models import Candle, MarketSnapshot, MarketStatistics, MarketSymbol, Subscription, Tick
from .validators import ValidationService
from .websocket import event_bus


class SymbolService:
    """Shared query boundary for the persisted broker instrument catalogue."""

    def catalogue(
        self, *, broker=None, active=True, tradable=None, market=None,
        sub_market=None, search=None, symbol=None,
    ):
        queryset = MarketSymbol.objects.all()
        if broker:
            queryset = queryset.filter(broker__iexact=str(broker).strip())
        if active is not None:
            queryset = queryset.filter(is_active=bool(active))
        if tradable is not None:
            queryset = queryset.filter(is_tradable=bool(tradable))
        if market:
            queryset = queryset.filter(market__iexact=str(market).strip())
        if sub_market:
            queryset = queryset.filter(sub_market__iexact=str(sub_market).strip())
        if symbol:
            queryset = queryset.filter(symbol__iexact=str(symbol).strip())
        if search:
            term = str(search).strip()
            if term:
                queryset = queryset.filter(
                    Q(symbol__icontains=term) | Q(display_name__icontains=term)
                )
        return queryset.order_by("market", "symbol")

    def symbols(self):
        return self.catalogue(active=None, tradable=None)

    def symbol(self, symbol):
        return self.catalogue(active=None, tradable=None, symbol=symbol).get()

    def search(self, q):
        return self.catalogue(active=None, tradable=None, search=q)

    def active(self):
        return self.catalogue(active=True, tradable=None)

    def inactive(self):
        return self.catalogue(active=False, tradable=None)

    def favorite(self, user=None):
        return self.active()

    def market(self, market):
        return self.catalogue(active=None, tradable=None, market=market)

    def submarket(self, submarket):
        return self.catalogue(active=None, tradable=None, sub_market=submarket)


class CandleService:
    def bucket_epoch(self, epoch, seconds): return epoch if seconds == 0 else epoch - (epoch % seconds)
    def update_from_tick(self, tick):
        made=[]
        for timeframe, seconds in TIMEFRAMES.items():
            epoch = self.bucket_epoch(tick.epoch, seconds)
            try:
                candle, created = Candle.objects.get_or_create(
                    symbol=tick.symbol,
                    timeframe=timeframe,
                    epoch=epoch,
                    defaults={"open": tick.quote, "high": tick.quote, "low": tick.quote, "close": tick.quote, "volume": tick.volume, "source": "tick_stream"},
                )
            except IntegrityError:
                candle = Candle.objects.get(symbol=tick.symbol, timeframe=timeframe, epoch=epoch)
                created = False
            if not created and not (
                candle.source in {"deriv_candles", "connected_broker"} and TIMEFRAMES.get(timeframe, 0) >= 60
            ):
                candle.high=max(candle.high,tick.quote); candle.low=min(candle.low,tick.quote); candle.close=tick.quote; candle.volume += tick.volume; candle.save(update_fields=["high","low","close","volume"])
            MarketCacheService().set_latest_candle(tick.symbol.symbol, timeframe, self.serialize(candle))
            # A candle is closed when the first tick in the next bucket arrives.
            # Publish the prior bucket once, not every tick update to the live
            # candle, so downstream AI inference is event-driven and bounded.
            if created:
                previous = Candle.objects.filter(
                    symbol=tick.symbol, timeframe=timeframe, epoch__lt=epoch
                ).order_by("-epoch").first()
                if previous:
                    event_bus.publish(EVENT_NEW_CANDLE, self.serialize(previous))
            made.append(candle)
        return made
    def serialize(self,c): return {"symbol": c.symbol.symbol, "timeframe": c.timeframe, "open": str(c.open), "high": str(c.high), "low": str(c.low), "close": str(c.close), "volume": str(c.volume), "epoch": c.epoch, "source": c.source}


class TickService:
    def ingest(self, data):
        # Broker feeds commonly repeat the same quote. Treat an identical
        # (symbol, epoch, quote) as an idempotent event, including races between
        # multiple workers. The database unique constraint remains authoritative.
        symbol_value = data.get("symbol")
        epoch = data.get("epoch")
        quote = data.get("quote")
        if symbol_value and epoch is not None and quote is not None:
            existing = Tick.objects.filter(
                symbol__symbol=symbol_value,
                epoch=int(epoch),
                quote=Decimal(str(quote)),
            ).select_related("symbol").first()
            if existing:
                return existing

        clean = ValidationService().validate_tick(data)
        spread = max(Decimal("0"), clean["ask"] - clean["bid"]) if clean["bid"] is not None and clean["ask"] is not None else Decimal("0")
        try:
            # Use an inner savepoint so a uniqueness race does not poison the
            # request transaction before we read the winning row.
            with transaction.atomic():
                tick = Tick.objects.create(**clean, spread=spread, received_at=timezone.now())
        except IntegrityError:
            tick = Tick.objects.get(
                symbol=clean["symbol"],
                epoch=clean["epoch"],
                quote=clean["quote"],
            )
            return tick

        payload = self.serialize(tick)
        MarketCacheService().set_latest_tick(tick.symbol.symbol, payload)
        self.update_snapshot(tick)
        event_bus.publish(EVENT_TICK_RECEIVED, payload)
        CandleService().update_from_tick(tick)
        return tick

    def update_snapshot(self,tick):
        defaults={"last_price":tick.quote,"bid":tick.bid,"ask":tick.ask,"spread":tick.spread,"bid_ask_source":tick.bid_ask_source,"timestamp":timezone.now()}
        snap,_=MarketSnapshot.objects.get_or_create(symbol=tick.symbol, defaults={**defaults,"high":tick.quote,"low":tick.quote,"volume":tick.volume})
        if snap.pk:
            snap.last_price=tick.quote; snap.bid=tick.bid; snap.ask=tick.ask; snap.spread=tick.spread; snap.bid_ask_source=tick.bid_ask_source; snap.high=max(snap.high,tick.quote); snap.low=min(snap.low,tick.quote); snap.volume += tick.volume; snap.timestamp=timezone.now(); snap.save()
        MarketCacheService().set_snapshot(tick.symbol.symbol, {"last_price": str(snap.last_price), "bid": str(snap.bid) if snap.bid_ask_source in {"broker", "partial"} and snap.bid is not None else None, "ask": str(snap.ask) if snap.bid_ask_source in {"broker", "partial"} and snap.ask is not None else None, "spread": str(snap.spread) if snap.bid_ask_source == "broker" and snap.bid is not None and snap.ask is not None else None, "bid_ask_source": snap.bid_ask_source, "bid_ask_available": snap.bid_ask_source == "broker" and snap.bid is not None and snap.ask is not None})

    def serialize(self,t):
        source = getattr(t, "bid_ask_source", "unknown")
        has_bid_ask = source in {"broker", "partial"}
        complete = source == "broker" and t.bid is not None and t.ask is not None
        return {
            "symbol": t.symbol.symbol,
            "bid": str(t.bid) if has_bid_ask and t.bid is not None else None,
            "ask": str(t.ask) if has_bid_ask and t.ask is not None else None,
            "quote": str(t.quote),
            "spread": str(t.spread) if complete else None,
            "bid_ask_source": source,
            "bid_ask_available": complete,
            "epoch": t.epoch,
            "volume": str(t.volume),
        }


class HistoricalDataService:
    def tick_history(self, symbol, limit=1000): return Tick.objects.filter(symbol__symbol=symbol).order_by("-epoch")[:limit]
    def candle_history(self, symbol, timeframe="1m", limit=1000): return Candle.objects.filter(symbol__symbol=symbol,timeframe=timeframe).order_by("-epoch")[:limit]
    def export(self, queryset): return list(queryset.values())
    def compress(self): return None
    def incremental_updates(self, symbol, since_epoch): return Tick.objects.filter(symbol__symbol=symbol, epoch__gt=since_epoch)


class MarketStatisticsService:
    def calculate(self, symbol):
        sym = MarketSymbol.objects.get(symbol=symbol) if isinstance(symbol,str) else symbol
        ticks = Tick.objects.filter(symbol=sym)
        agg = ticks.aggregate(high=Max("quote"), low=Min("quote"), high_vol=Max("volume"), count=Count("id"), avg_vol=Avg("volume"))
        spread_agg = ticks.filter(bid_ask_source="broker").aggregate(avg_spread=Avg("spread"), sample_count=Count("id"))
        return MarketStatistics.objects.create(
            symbol=sym,
            average_spread=spread_agg["avg_spread"] or 0,
            spread_sample_count=spread_agg["sample_count"] or 0,
            highest_price=agg["high"] or 0,
            lowest_price=agg["low"] or 0,
            highest_volume=agg["high_vol"] or 0,
            tick_count=agg["count"] or 0,
            average_volume=agg["avg_vol"] or 0,
        )


class SubscriptionService:
    def add(self,user,symbol,timeframe="tick"):
        sub,_=Subscription.objects.get_or_create(user=user,symbol=MarketSymbol.objects.get(symbol=symbol),timeframe=timeframe,defaults={"status":"active"}); event_bus.publish(EVENT_SUBSCRIPTION_ADDED,{"symbol":symbol,"timeframe":timeframe}); return sub
    def remove(self,user,symbol,timeframe="tick"):
        Subscription.objects.filter(user=user,symbol__symbol=symbol,timeframe=timeframe).update(status="cancelled"); event_bus.publish(EVENT_SUBSCRIPTION_REMOVED,{"symbol":symbol,"timeframe":timeframe})


class MarketDataService:
    tick_service=TickService(); candle_service=CandleService(); symbols=SymbolService(); history=HistoricalDataService(); stats=MarketStatisticsService(); subscriptions=SubscriptionService()
