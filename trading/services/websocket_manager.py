import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

import websockets

logger = logging.getLogger(__name__)

DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"


class WebSocketManager:
    """Manages Deriv's public market-data WebSocket with reconnects/subscriptions."""

    def __init__(self, uri: str = DERIV_PUBLIC_WS):
        self.uri = uri or DERIV_PUBLIC_WS
        self.ws = None
        self.session_id = str(uuid.uuid4())
        self.subscriptions: Dict[str, dict] = {}
        self.message_handlers: List[Callable] = []
        self.is_connected = False
        self.reconnect_delay = 3
        self.max_retries = 5
        self.retry_count = 0
        self.app_id = None
        self._listener_task = None
        self._closing = False

    async def connect(self, app_id: str | None = None):
        """Connect to public market data.

        The current public Deriv endpoint does not require authentication or an
        app_id query parameter. Authenticated trading connections are created
        separately through the account OTP flow in the broker adapter.
        """
        if self.is_connected and self.ws:
            return
        self.app_id = app_id
        self._closing = False
        try:
            self.ws = await websockets.connect(
                self.uri,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=10,
            )
            self.is_connected = True
            self.retry_count = 0
            self._listener_task = asyncio.create_task(self._listen())
            for subscription in list(self.subscriptions.values()):
                await self._subscribe(subscription)
        except Exception:
            self.is_connected = False
            self.ws = None
            logger.exception("Deriv public market-data WebSocket connection failed")
            await self._reconnect(app_id)

    async def _reconnect(self, app_id: str | None = None):
        if self._closing or self.retry_count >= self.max_retries:
            return
        self.retry_count += 1
        await asyncio.sleep(self.reconnect_delay)
        await self.connect(app_id)

    async def _subscribe(self, subscription):
        if not self.ws or not self.is_connected:
            raise ConnectionError("WebSocket is not connected")
        if subscription["type"] == "ticks":
            await self.ws.send(json.dumps({"ticks": subscription["symbol"], "subscribe": 1, "req_id": subscription["id"]}))

    async def subscribe_ticks(self, symbol: str):
        if not symbol:
            raise ValueError("A market symbol is required")
        subscription_id = f"tick_{symbol}"
        if subscription_id in self.subscriptions:
            return self.subscriptions[subscription_id]
        if not self.is_connected or not self.ws:
            raise ConnectionError("WebSocket is not connected")
        self.subscriptions[subscription_id] = {"id": subscription_id, "type": "ticks", "symbol": symbol, "subscribed_at": datetime.now().isoformat()}
        await self._subscribe(self.subscriptions[subscription_id])
        return self.subscriptions[subscription_id]

    async def subscribe_candles(self, symbol: str, granularity: int = 60):
        return await self.subscribe_ticks(symbol)

    async def unsubscribe(self, symbol: str):
        for sub_id in [k for k, v in self.subscriptions.items() if v["symbol"] == symbol]:
            if self.is_connected and self.ws:
                await self.ws.send(json.dumps({"forget": sub_id}))
            self.subscriptions.pop(sub_id, None)

    def register_handler(self, handler: Callable):
        self.message_handlers.append(handler)

    async def _listen(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                if data.get("error"):
                    logger.warning("Deriv websocket error: %s", data["error"])
                for handler in self.message_handlers:
                    try:
                        result = handler(data)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception("WebSocket handler error")
        except Exception:
            self.is_connected = False
            if not self._closing:
                logger.exception("WebSocket listener stopped; reconnecting")
                await self._reconnect(self.app_id)

    async def disconnect(self):
        self._closing = True
        if self._listener_task and self._listener_task is not asyncio.current_task():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
        self.is_connected = False
        self.ws = None

    def get_subscriptions(self) -> Dict:
        return self.subscriptions

    def is_subscribed(self, symbol: str) -> bool:
        return any(v["symbol"] == symbol for v in self.subscriptions.values())


class StreamAggregator:
    def __init__(self):
        self.candle_buffers: Dict[str, List] = {}
        self.latest_candles: Dict[str, dict] = {}

    def add_tick(self, symbol: str, timeframe: str, tick: dict):
        self.candle_buffers.setdefault(f"{symbol}:{timeframe}", []).append(tick)

    def get_current_candle(self, symbol: str, timeframe: str) -> Optional[dict]:
        return self.latest_candles.get(f"{symbol}:{timeframe}")

    def finalize_candle(self, symbol: str, timeframe: str) -> Optional[dict]:
        key = f"{symbol}:{timeframe}"
        ticks = self.candle_buffers.get(key, [])
        if not ticks:
            return None
        prices = [t["price"] for t in ticks]
        candle = {"open": prices[0], "high": max(prices), "low": min(prices), "close": prices[-1], "volume": len(ticks), "time": datetime.now().isoformat()}
        self.latest_candles[key] = candle
        self.candle_buffers[key] = []
        return candle
