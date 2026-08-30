from __future__ import annotations

import asyncio
import json

import websockets
from django.conf import settings
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from apps.market_data.deriv_sync import DERIV_PUBLIC_WS, sync_active_symbols
from apps.market_data.models import MarketSymbol
from apps.market_data.services import MarketDataService


class Command(BaseCommand):
    help = "Maintain the authoritative Deriv market catalogue and public tick stream."

    def handle(self, *args, **options):
        asyncio.run(self.run())

    async def run(self):
        await sync_to_async(sync_active_symbols)()
        symbols = await sync_to_async(list)(MarketSymbol.objects.filter(broker="deriv", is_active=True).values_list("symbol", flat=True))
        if not symbols:
            raise RuntimeError("No active Deriv markets are available")
        url = getattr(settings, "DERIV_PUBLIC_WS_URL", DERIV_PUBLIC_WS)
        layer = get_channel_layer()
        while True:
            try:
                async with websockets.connect(url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=10, max_size=2**20) as ws:
                    req_id = 1
                    for symbol in symbols:
                        await ws.send(json.dumps({"ticks": symbol, "subscribe": 1, "req_id": req_id}))
                        req_id += 1
                    while True:
                        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=75))
                        if message.get("error"):
                            continue
                        if message.get("msg_type") != "tick":
                            continue
                        tick = message.get("tick") or {}
                        symbol = str(tick.get("symbol") or "")
                        quote = tick.get("quote")
                        epoch = tick.get("epoch")
                        if not symbol or quote is None or epoch is None:
                            continue
                        payload = await sync_to_async(self.ingest)(tick)
                        if layer and payload:
                            await layer.group_send(
                                f"algobot-market-{symbol}",
                                {"type": "broker.event", "event_type": "market.tick", "payload": payload},
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stderr.write(f"market stream reconnecting: {exc}")
                await asyncio.sleep(2)

    @staticmethod
    def ingest(tick):
        return MarketDataService().tick_service.ingest({
            "symbol": tick.get("symbol"),
            "quote": tick.get("quote"),
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "epoch": tick.get("epoch"),
            "volume": tick.get("volume", 0),
        })
