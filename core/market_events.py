from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone


class MarketEventConsumer(AsyncJsonWebsocketConsumer):
    """Subscribe authenticated clients to server-authoritative market ticks."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.market_group = None
        await self.accept()
        await self.send_json({"type": "connection.ready", "resource": "market-data", "source": "canonical_market_event_bus", "timestamp": timezone.now().timestamp()})

    async def disconnect(self, close_code):
        if self.market_group:
            await self.channel_layer.group_discard(self.market_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = str(content.get("action") or "").lower()
        if action == "ping":
            await self.send_json({"type": "pong", "timestamp": timezone.now().timestamp()})
            return
        if action == "subscribe":
            symbol = str(content.get("symbol") or "").strip()
            if not symbol or len(symbol) > 40 or not await self.symbol_exists(symbol):
                await self.send_json({"type": "error", "error": {"code": "UNKNOWN_SYMBOL", "message": "The requested market symbol is not available."}})
                return
            if self.market_group:
                await self.channel_layer.group_discard(self.market_group, self.channel_name)
            self.market_group = f"algobot-market-{symbol}"
            await self.channel_layer.group_add(self.market_group, self.channel_name)
            await self.send_json({"type": "market.subscription", "symbol": symbol, "status": "subscribed", "source": "canonical_market_event_bus"})
            return
        if action == "unsubscribe":
            if self.market_group:
                await self.channel_layer.group_discard(self.market_group, self.channel_name)
                self.market_group = None
            await self.send_json({"type": "subscription", "status": "unsubscribed"})
            return
        await self.send_json({"type": "error", "error": {"code": "UNSUPPORTED_ACTION", "message": "Unsupported websocket action."}})

    @database_sync_to_async
    def symbol_exists(self, symbol):
        from apps.market_data.models import MarketSymbol
        return MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists()

    async def broker_event(self, event):
        await self.send_json({"type": event.get("event_type", "broker.event"), "payload": event.get("payload") or {}, "source": "broker", "timestamp": timezone.now().timestamp()})
