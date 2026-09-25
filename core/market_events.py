from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone


class MarketEventConsumer(AsyncJsonWebsocketConsumer):
    """Subscribe authenticated clients to server-authoritative market ticks."""

    MAX_SYMBOLS = 20

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.market_groups = set()
        await self.accept()
        await self.send_json(
            {
                "type": "connection.ready",
                "resource": "market-data",
                "source": "canonical_market_event_bus",
                "timestamp": timezone.now().timestamp(),
            }
        )

    async def disconnect(self, close_code):
        for group in self.market_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        self.market_groups.clear()

    async def receive_json(self, content, **kwargs):
        action = str(content.get("action") or "").lower()
        if action == "ping":
            await self.send_json({"type": "pong", "timestamp": timezone.now().timestamp()})
            return

        if action == "subscribe":
            raw_symbols = content.get("symbols")
            if raw_symbols is None:
                raw_symbols = [content.get("symbol")]
            if not isinstance(raw_symbols, list):
                raw_symbols = [raw_symbols]

            symbols = []
            for raw in raw_symbols[: self.MAX_SYMBOLS]:
                symbol = str(raw or "").strip()
                if symbol and len(symbol) <= 40 and symbol not in symbols:
                    symbols.append(symbol)

            if not symbols:
                await self.send_json(
                    {
                        "type": "error",
                        "error": {
                            "code": "UNKNOWN_SYMBOL",
                            "message": "At least one valid market symbol is required.",
                        },
                    }
                )
                return

            invalid = [
                symbol
                for symbol in symbols
                if not await self.symbol_exists(symbol)
            ]
            if invalid:
                await self.send_json(
                    {
                        "type": "error",
                        "error": {
                            "code": "UNKNOWN_SYMBOL",
                            "message": "One or more requested market symbols are unavailable.",
                            "symbols": invalid,
                        },
                    }
                )
                return

            for group in self.market_groups:
                await self.channel_layer.group_discard(group, self.channel_name)
            self.market_groups = {
                f"algobot-market-{symbol}" for symbol in symbols
            }
            for group in self.market_groups:
                await self.channel_layer.group_add(group, self.channel_name)

            await self.send_json(
                {
                    "type": "market.subscription",
                    "symbols": symbols,
                    "status": "subscribed",
                    "source": "canonical_market_event_bus",
                }
            )
            return

        if action == "unsubscribe":
            for group in self.market_groups:
                await self.channel_layer.group_discard(group, self.channel_name)
            self.market_groups.clear()
            await self.send_json({"type": "subscription", "status": "unsubscribed"})
            return

        await self.send_json(
            {
                "type": "error",
                "error": {
                    "code": "UNSUPPORTED_ACTION",
                    "message": "Unsupported websocket action.",
                },
            }
        )

    @database_sync_to_async
    def symbol_exists(self, symbol):
        from apps.market_data.models import MarketSymbol

        return MarketSymbol.objects.filter(
            broker="deriv",
            symbol=symbol,
            is_active=True,
            is_tradable=True,
        ).exists()

    async def broker_event(self, event):
        await self.send_json(
            {
                "type": event.get("event_type", "broker.event"),
                "payload": event.get("payload") or {},
                "source": "broker",
                "timestamp": timezone.now().timestamp(),
            }
        )
