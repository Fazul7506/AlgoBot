import asyncio
import json
import logging
import websockets
import uuid
from typing import Dict, Optional, List, Callable
from django.utils import timezone
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages real-time websocket connections for market data streaming"""
    
    def __init__(self, uri: str = "wss://ws.binaryws.com/websockets/v3"):
        self.uri = uri
        self.ws = None
        self.session_id = str(uuid.uuid4())
        self.subscriptions: Dict[str, dict] = {}
        self.message_handlers: List[Callable] = []
        self.is_connected = False
        self.reconnect_delay = 3
        self.max_retries = 5
        self.retry_count = 0
    
    async def connect(self, app_id: str):
        """Connect to websocket"""
        try:
            self.ws = await websockets.connect(self.uri)
            
            # Authorize with app_id
            await self.ws.send(json.dumps({"authorize": app_id}))
            response = json.loads(await self.ws.recv())
            
            if "error" in response:
                raise Exception(f"Authorization failed: {response['error']}")
            
            self.is_connected = True
            self.retry_count = 0
            logger.info(f"WebSocket connected: {self.session_id}")
            
            # Start listening for messages
            asyncio.create_task(self._listen())
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            await self._reconnect(app_id)
    
    async def _reconnect(self, app_id: str):
        """Reconnect to websocket on failure"""
        if self.retry_count >= self.max_retries:
            logger.error("Max reconnection retries reached")
            return
        
        self.retry_count += 1
        await asyncio.sleep(self.reconnect_delay)
        await self.connect(app_id)
    
    async def subscribe_ticks(self, symbol: str):
        """Subscribe to tick stream"""
        try:
            subscription_id = f"tick_{symbol}"
            
            await self.ws.send(json.dumps({
                "ticks": symbol,
                "subscribe": 1,
                "req_id": subscription_id
            }))
            
            self.subscriptions[subscription_id] = {
                'type': 'ticks',
                'symbol': symbol,
                'subscribed_at': datetime.now().isoformat()
            }
            
            logger.info(f"Subscribed to ticks: {symbol}")
        except Exception as e:
            logger.error(f"Tick subscription error: {e}")
    
    async def subscribe_candles(self, symbol: str, granularity: int = 60):
        """Subscribe to candle stream"""
        try:
            subscription_id = f"candle_{symbol}_{granularity}"
            
            await self.ws.send(json.dumps({
                "proposal": 1,
                "subscribe": 1,
                "symbol": symbol,
                "parameters": {
                    "contract_type": "CALL",
                    "currency": "USD",
                    "amount": 1,
                    "duration_unit": "m",
                    "duration": 1
                },
                "req_id": subscription_id
            }))
            
            self.subscriptions[subscription_id] = {
                'type': 'candles',
                'symbol': symbol,
                'granularity': granularity,
                'subscribed_at': datetime.now().isoformat()
            }
            
            logger.info(f"Subscribed to candles: {symbol} {granularity}s")
        except Exception as e:
            logger.error(f"Candle subscription error: {e}")
    
    async def unsubscribe(self, symbol: str):
        """Unsubscribe from symbol"""
        try:
            subscription_ids = [k for k, v in self.subscriptions.items() if v['symbol'] == symbol]
            
            for sub_id in subscription_ids:
                await self.ws.send(json.dumps({
                    "forget": sub_id
                }))
                del self.subscriptions[sub_id]
            
            logger.info(f"Unsubscribed from: {symbol}")
        except Exception as e:
            logger.error(f"Unsubscribe error: {e}")
    
    def register_handler(self, handler: Callable):
        """Register message handler"""
        self.message_handlers.append(handler)
    
    async def _listen(self):
        """Listen for incoming websocket messages"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                
                # Call all registered handlers
                for handler in self.message_handlers:
                    try:
                        handler(data)
                    except Exception as e:
                        logger.error(f"Handler error: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Listen error: {e}")
            self.is_connected = False
    
    async def disconnect(self):
        """Disconnect from websocket"""
        try:
            if self.ws:
                await self.ws.close()
            self.is_connected = False
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
    
    def get_subscriptions(self) -> Dict:
        """Get current subscriptions"""
        return self.subscriptions
    
    def is_subscribed(self, symbol: str) -> bool:
        """Check if subscribed to symbol"""
        return any(v['symbol'] == symbol for v in self.subscriptions.values())


class StreamAggregator:
    """Aggregate streaming tick data into candles in real-time"""
    
    def __init__(self):
        self.candle_buffers: Dict[str, List] = {}
        self.latest_candles: Dict[str, dict] = {}
    
    def add_tick(self, symbol: str, timeframe: str, tick: dict):
        """Add tick to candle buffer"""
        key = f"{symbol}:{timeframe}"
        
        if key not in self.candle_buffers:
            self.candle_buffers[key] = []
        
        self.candle_buffers[key].append(tick)
    
    def get_current_candle(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Get current candle in formation"""
        key = f"{symbol}:{timeframe}"
        return self.latest_candles.get(key)
    
    def finalize_candle(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Finalize current candle"""
        key = f"{symbol}:{timeframe}"
        ticks = self.candle_buffers.get(key, [])
        
        if not ticks:
            return None
        
        prices = [t['price'] for t in ticks]
        candle = {
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': len(ticks),
            'time': datetime.now().isoformat()
        }
        
        self.latest_candles[key] = candle
        self.candle_buffers[key] = []
        
        return candle
