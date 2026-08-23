"""Deriv WebSocket transport used by the isolated Deriv broker adapter."""
import asyncio, json, logging, time, uuid
from collections import deque
from typing import Any, Awaitable, Callable
import websockets
from .constants import DERIV_WS_URL

logger = logging.getLogger(__name__)
Handler = Callable[[dict[str, Any]], Awaitable[None] | None]

class DerivWebSocketEngine:
    def __init__(self, app_id: str | None = None, uri: str = DERIV_WS_URL, reconnect_delay: float = 3.0):
        self.app_id = app_id; self.uri = uri or DERIV_WS_URL; self.websocket = None; self.connected = False
        self.subscriptions = {}; self.handlers: list[Handler] = []; self.retry_queue = deque(); self.seen: set[str] = set()
        self.pending: dict[str, asyncio.Future] = {}; self.latency_ms: float | None = None; self.reconnect_delay = reconnect_delay

    def add_handler(self, handler: Handler) -> None: self.handlers.append(handler)
    async def connect(self) -> None:
        self.websocket = await websockets.connect(self.uri, ping_interval=None); self.connected = True
        asyncio.create_task(self._listen()); asyncio.create_task(self.heartbeat())
    async def disconnect(self) -> None:
        self.connected = False
        if self.websocket: await self.websocket.close()
        for future in self.pending.values():
            if not future.done(): future.cancel()
        self.pending.clear()
    def _new_req_id(self, payload: dict[str, Any]) -> str: return str(payload.get("req_id") or uuid.uuid4().int % 2147483647)
    async def send(self, payload: dict[str, Any]) -> str:
        req_id = self._new_req_id(payload); payload["req_id"] = req_id
        if not self.connected or not self.websocket: self.retry_queue.append(payload); return req_id
        await self.websocket.send(json.dumps(payload)); return req_id
    async def request(self, payload: dict[str, Any]) -> str: return await self.send(payload)
    async def request_response(self, payload: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
        req_id = self._new_req_id(payload); payload["req_id"] = req_id
        loop = asyncio.get_running_loop(); future = loop.create_future(); self.pending[req_id] = future
        try:
            if not self.connected or not self.websocket: await self.connect()
            await self.websocket.send(json.dumps(payload)); return await asyncio.wait_for(future, timeout=timeout)
        finally: self.pending.pop(req_id, None)
    async def authorize(self, token: str) -> str:
        raise RuntimeError("Authenticated Deriv sockets require the broker OTP flow; the public market socket cannot authorize tokens")
    async def ping(self) -> float:
        start = time.perf_counter(); response = await self.request_response({"ping": 1}, timeout=8)
        self.latency_ms = (time.perf_counter() - start) * 1000
        if response.get("error"): raise RuntimeError(response["error"].get("message", "Deriv ping failed"))
        return self.latency_ms
    async def heartbeat(self) -> None:
        while self.connected:
            try: await self.ping()
            except Exception:
                logger.exception("Deriv heartbeat failed"); await self.reconnect()
            await asyncio.sleep(20)
    async def subscribe(self, symbol: str) -> str:
        req_id = await self.send({"ticks": symbol, "subscribe": 1}); self.subscriptions[symbol] = req_id; return req_id
    async def unsubscribe(self, symbol: str) -> None:
        req_id = self.subscriptions.pop(symbol, None)
        if req_id: await self.send({"forget": req_id})
    async def reconnect(self) -> None:
        self.connected = False; await asyncio.sleep(self.reconnect_delay); await self.connect()
        for payload in list(self.retry_queue): await self.send(payload)
        self.retry_queue.clear()
    async def _listen(self) -> None:
        try:
            async for raw in self.websocket:
                digest = str(hash(raw))
                if digest in self.seen: continue
                self.seen.add(digest); data = json.loads(raw); req_id = data.get("req_id")
                future = self.pending.get(str(req_id)) if req_id is not None else None
                if future and not future.done(): future.set_result(data)
                for handler in self.handlers:
                    result = handler(data)
                    if asyncio.iscoroutine(result): await result
        except Exception:
            logger.exception("Deriv websocket listener failed")
            if self.connected: await self.reconnect()

class DerivSubscriptionManager:
    def __init__(self, engine: DerivWebSocketEngine, symbols: list[str] | None = None):
        self.engine = engine; self.symbols = symbols or []; self.paused = False
    async def subscribe(self, symbol: str):
        if symbol not in self.symbols: self.symbols.append(symbol)
        return await self.engine.subscribe(symbol)
    async def unsubscribe(self, symbol: str):
        await self.engine.unsubscribe(symbol); self.symbols = [s for s in self.symbols if s != symbol]
    async def subscribe_all(self):
        for symbol in self.symbols: await self.engine.subscribe(symbol)
    def pause_stream(self): self.paused = True
    async def resume_stream(self): self.paused = False; await self.subscribe_all()
