from __future__ import annotations

import asyncio
from decimal import Decimal

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone


class AuthenticatedStateConsumer(AsyncJsonWebsocketConsumer):
    """Authenticated, broker-independent websocket endpoint.

    The browser subscribes to resources and receives authoritative data already
    persisted by backend services. No broker API is called from the websocket layer.
    """

    resource = ""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.symbol = None
        self._poll_task = None
        await self.accept()
        await self.send_json({"type": "connection.ready", "resource": self.resource, "timestamp": timezone.now().timestamp()})

    async def disconnect(self, close_code):
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "subscribe" and self.resource == "market-data":
            symbol = str(content.get("symbol") or "").strip()
            if not symbol or len(symbol) > 40:
                await self.send_json({"type": "error", "error": {"code": "INVALID_SYMBOL", "message": "A valid market symbol is required."}})
                return
            exists = await self.symbol_exists(symbol)
            if not exists:
                await self.send_json({"type": "error", "error": {"code": "UNKNOWN_SYMBOL", "message": "The requested market symbol is not available."}})
                return
            self.symbol = symbol
            if self._poll_task:
                self._poll_task.cancel()
            self._poll_task = asyncio.create_task(self._market_loop())
            await self.send_json({"type": "market.subscription", "symbol": symbol, "status": "subscribed"})
            return
        if action == "unsubscribe":
            self.symbol = None
            if self._poll_task:
                self._poll_task.cancel()
                self._poll_task = None
            await self.send_json({"type": "subscription", "status": "unsubscribed"})
            return
        if action == "ping":
            await self.send_json({"type": "pong", "timestamp": timezone.now().timestamp()})
            return
        await self.send_json({"type": "error", "error": {"code": "UNSUPPORTED_ACTION", "message": "Unsupported websocket action."}})

    async def _market_loop(self):
        last_epoch = None
        while True:
            if not self.symbol:
                return
            # Fetch through the selected broker account before broadcasting.
            # The WebSocket is therefore a real-time view of broker data rather
            # than a passive stream of whichever historical tick happened to be
            # in the database.
            tick = await self.live_tick(self.symbol)
            if tick and tick["epoch"] != last_epoch:
                last_epoch = tick["epoch"]
                await self.send_json({"type": "market.tick", **tick})
            await asyncio.sleep(1)

    @database_sync_to_async
    def symbol_exists(self, symbol):
        from apps.market_data.models import MarketSymbol
        return MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists()

    @database_sync_to_async
    def live_tick(self, symbol):
        from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
        from apps.brokers.models import BrokerAccount
        from apps.brokers.services import BrokerRegistry
        from apps.market_data.deriv_sync import fetch_tick
        from apps.market_data.services import MarketDataService
        from apps.market_data.models import Tick

        account = (
            BrokerAccount.objects.filter(user=self.scope["user"], status="active", broker__status="active")
            .select_related("broker").order_by("-is_preferred", "-id").first()
        )
        try:
            if not account:
                return None
            if account.broker.broker_type == "deriv":
                data = fetch_tick(symbol)
            else:
                data = asyncio.run(asyncio.wait_for(BrokerRegistry().adapter(account.broker, account).get_market_data(symbol), timeout=7))
            tick = MarketDataService().tick_service.ingest({
                "symbol": symbol,
                "quote": data.get("price", data.get("quote")),
                "bid": data.get("bid"), "ask": data.get("ask"),
                "epoch": data.get("epoch"), "volume": data.get("volume", 0),
            })
        except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError, RuntimeError, OSError, ValueError, TimeoutError):
            # Preserve the last known quote during a temporary broker outage;
            # clients can keep their chart visible while reconnecting.
            tick = Tick.objects.filter(symbol__symbol=symbol).select_related("symbol").order_by("-epoch", "-id").first()
        if not tick:
            return None
        return {
            "symbol": symbol,
            "price": float(tick.quote),
            "bid": float(tick.bid) if tick.bid is not None else None,
            "ask": float(tick.ask) if tick.ask is not None else None,
            "timestamp": tick.received_at.timestamp() if tick.received_at else float(tick.epoch),
            "epoch": tick.epoch,
        }


class MarketDataConsumer(AuthenticatedStateConsumer):
    resource = "market-data"


class PortfolioConsumer(AuthenticatedStateConsumer):
    resource = "portfolio"

    async def connect(self):
        await super().connect()
        if self.scope.get("user") and self.scope["user"].is_authenticated:
            await self.send_json({"type": "portfolio.update", **await self.portfolio_state()})

    @database_sync_to_async
    def portfolio_state(self):
        from apps.portfolio.models import Portfolio
        portfolio = Portfolio.objects.filter(user=self.scope["user"], status="active").order_by("-updated_at").first()
        if not portfolio:
            return {"status": "empty", "balance": None, "equity": None, "margin": None, "unrealized_pnl": None}
        metadata = portfolio.metadata or {}
        return {
            "status": "ready",
            "balance": str(portfolio.current_balance),
            "equity": str(portfolio.equity),
            "margin": metadata.get("margin"),
            "unrealized_pnl": metadata.get("unrealized_pnl"),
            "currency": portfolio.currency,
            "timestamp": portfolio.updated_at.timestamp(),
        }


class NotificationConsumer(AuthenticatedStateConsumer):
    resource = "notifications"

    async def connect(self):
        await super().connect()
        if self.scope.get("user") and self.scope["user"].is_authenticated:
            await self.send_json({"type": "notification.snapshot", "notifications": await self.latest_notifications()})

    @database_sync_to_async
    def latest_notifications(self):
        from apps.notifications.models import Notification
        rows = Notification.objects.filter(user=self.scope["user"]).order_by("-created_at")[:20]
        return [
            {
                "id": row.pk,
                "type": "notification",
                "severity": row.priority,
                "title": row.title,
                "message": row.message,
                "timestamp": row.created_at.timestamp(),
                "read": row.read_at is not None,
            }
            for row in rows
        ]
