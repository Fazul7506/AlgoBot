import logging
import asyncio
import json
import redis
from typing import Dict, Optional, List
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from time import monotonic

logger = logging.getLogger(__name__)


class DataCacheManager:
    """Redis-based caching for market data"""
    
    def __init__(self, host='127.0.0.1', port=6379, db=0):
        # ALWAYS safe initialize fallback store
        self.memory_cache = {}
        self.memory_expiry = {}

        # FEATURE TOGGLE (KEY FIX)
        if not getattr(settings, "USE_REDIS", False):
            logger.info("Redis disabled via settings - using in-memory cache only")
            self.redis_client = None
            return

        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self.redis_client.ping()
            logger.info("Redis connection established")

        except redis.exceptions.ConnectionError:
            logger.warning("Redis not available - using in-memory cache")
            self.redis_client = None

        except Exception:
            logger.exception("Unexpected Redis error; using in-memory cache")
            self.redis_client = None
    
    def set_price(self, symbol: str, bid: float, ask: float, expiry: int = 60) -> bool:
        """Cache current price with expiry"""
        try:
            key = f"price:{symbol}"
            data = json.dumps({
                'bid': bid,
                'ask': ask,
                'timestamp': datetime.now().isoformat()
            })
            
            if self.redis_client:
                self.redis_client.setex(key, expiry, data)
            else:
                self.memory_cache[key] = data
                self.memory_expiry[key] = monotonic() + max(0, expiry)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def get_price(self, symbol: str) -> Optional[Dict]:
        """Get cached price"""
        try:
            key = f"price:{symbol}"
            if self.redis_client:
                data = self.redis_client.get(key)
            else:
                data = self.memory_cache.get(key)
                expires_at = self.memory_expiry.get(key)
                if expires_at is not None and monotonic() >= expires_at:
                    self.memory_cache.pop(key, None)
                    self.memory_expiry.pop(key, None)
                    data = None
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set_snapshot(self, symbol: str, snapshot: dict, expiry: int = 300) -> bool:
        """Cache market snapshot"""
        try:
            key = f"snapshot:{symbol}"
            data = json.dumps(snapshot)
            
            if self.redis_client:
                self.redis_client.setex(key, expiry, data)
            else:
                self.memory_cache[key] = data
                self.memory_expiry[key] = monotonic() + max(0, expiry)
            return True
        except Exception as e:
            logger.error(f"Snapshot cache error: {e}")
            return False
    
    def get_snapshot(self, symbol: str) -> Optional[Dict]:
        """Get market snapshot"""
        try:
            key = f"snapshot:{symbol}"
            if self.redis_client:
                data = self.redis_client.get(key)
            else:
                data = self.memory_cache.get(key)
                expires_at = self.memory_expiry.get(key)
                if expires_at is not None and monotonic() >= expires_at:
                    self.memory_cache.pop(key, None)
                    self.memory_expiry.pop(key, None)
                    data = None
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Snapshot get error: {e}")
            return None
    
    def set_candle(self, symbol: str, timeframe: str, candle: dict, expiry: int = 3600) -> bool:
        """Cache candle data"""
        try:
            key = f"candle:{symbol}:{timeframe}"
            data = json.dumps(candle)
            
            if self.redis_client:
                self.redis_client.setex(key, expiry, data)
            else:
                self.memory_cache[key] = data
                self.memory_expiry[key] = monotonic() + max(0, expiry)
            return True
        except Exception as e:
            logger.error(f"Candle cache error: {e}")
            return False
    
    def get_candle(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """Get cached candle"""
        try:
            key = f"candle:{symbol}:{timeframe}"
            if self.redis_client:
                data = self.redis_client.get(key)
            else:
                data = self.memory_cache.get(key)
                expires_at = self.memory_expiry.get(key)
                if expires_at is not None and monotonic() >= expires_at:
                    self.memory_cache.pop(key, None)
                    self.memory_expiry.pop(key, None)
                    data = None
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Candle get error: {e}")
            return None
    
    def invalidate(self, pattern: str) -> bool:
        """Invalidate cached items by pattern"""
        try:
            if self.redis_client:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            else:
                keys_to_delete = [k for k in self.memory_cache.keys() if pattern in k]
                for k in keys_to_delete:
                    self.memory_cache.pop(k, None)
                    self.memory_expiry.pop(k, None)
            return True
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return False


class SymbolManager:
    """Manage market symbols and metadata"""
    
    def __init__(self):
        self.symbols_cache = {}
        self._load_symbols()
    
    def _load_symbols(self):
        """Load symbols from database"""
        try:
            from trading.models.market import MarketSymbol
            symbols = MarketSymbol.objects.filter(is_active=True)
            self.symbols_cache = {s.symbol: s for s in symbols}
            logger.info(f"Loaded {len(self.symbols_cache)} market symbols")
        except Exception as e:
            logger.error(f"Symbol load error: {e}")
    
    def get_symbol(self, symbol: str):
        """Get symbol object"""
        if symbol not in self.symbols_cache:
            self._load_symbols()
        return self.symbols_cache.get(symbol)
    
    def get_symbols_by_type(self, market_type: str) -> List:
        """Get all symbols of a market type"""
        return [s for s in self.symbols_cache.values() if s.market_type == market_type]
    
    def get_all_tradeable_symbols(self) -> List:
        """Get all tradeable symbols"""
        return [s for s in self.symbols_cache.values() if s.is_tradeable]
    
    def refresh(self):
        """Refresh symbol cache"""
        self._load_symbols()


class HistoricalDataAggregator:
    """Aggregate tick data into OHLC candles"""
    
    @staticmethod
    def aggregate_to_candle(ticks: List[dict], timeframe: str) -> Optional[dict]:
        """Aggregate tick list to OHLC candle"""
        if not ticks:
            return None
        
        prices = [t['price'] for t in ticks]
        
        candle = {
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': len(ticks),
            'tick_count': len(ticks)
        }
        
        return candle
    
    @staticmethod
    def get_candle_period(timeframe: str) -> timedelta:
        """Convert timeframe to timedelta"""
        mapping = {
            'M1': timedelta(minutes=1),
            'M5': timedelta(minutes=5),
            'M15': timedelta(minutes=15),
            'M30': timedelta(minutes=30),
            'H1': timedelta(hours=1),
            'H4': timedelta(hours=4),
            'D1': timedelta(days=1),
        }
        return mapping.get(timeframe, timedelta(minutes=1))
    
    @staticmethod
    def save_price_history(symbol_obj, timeframe: str, ohlc: dict, candle_time: datetime):
        """Save OHLC candle to database"""
        try:
            from trading.models.market import PriceHistory
            
            candle_end_time = candle_time + HistoricalDataAggregator.get_candle_period(timeframe)
            
            PriceHistory.objects.update_or_create(
                symbol=symbol_obj,
                timeframe=timeframe,
                candle_time=candle_time,
                defaults={
                    'open': ohlc['open'],
                    'high': ohlc['high'],
                    'low': ohlc['low'],
                    'close': ohlc['close'],
                    'volume': ohlc['volume'],
                    'tick_count': ohlc['tick_count'],
                    'candle_end_time': candle_end_time,
                }
            )
            return True
        except Exception as e:
            logger.error(f"Price history save error: {e}")
            return False
