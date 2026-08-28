from __future__ import annotations

import asyncio
import json

import websockets
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone


class AuthenticatedStateConsumer(AsyncJsonWebsocketConsumer):
    """Authenticated, broker-independent websocket endpoint.

    Browser clients receive authoritative state over a persistent websocket.
    REST remains available for initial snapshots and explicit user actions, but
    live account/contract state is not implemented as browser polling.
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
            if not await self.symbol_exists(symbol):
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
        while self.symbol:
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

        account = BrokerAccount.objects.filter(user=self.scope["user"], status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first()
        if not account:
            return None
        cache_key = f"algobot:realtime:broker-quote:{account.broker.broker_type}:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        tick = None
        try:
            if account.broker.broker_type == "deriv":
                data = fetch_tick(symbol)
            else:
                data = asyncio.run(asyncio.wait_for(BrokerRegistry().adapter(account.broker, account).get_market_data(symbol), timeout=7))
            tick = MarketDataService().tick_service.ingest({"symbol": symbol, "quote": data.get("price", data.get("quote")), "bid": data.get("bid"), "ask": data.get("ask"), "epoch": data.get("epoch"), "volume": data.get("volume", 0)})
        except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError, RuntimeError, OSError, ValueError, TimeoutError):
            tick = Tick.objects.filter(symbol__symbol=symbol).select_related("symbol").order_by("-epoch", "-id").first()
        if not tick:
            return None
        payload = {"symbol": symbol, "price": float(tick.quote), "bid": float(tick.bid) if tick.bid is not None else None, "ask": float(tick.ask) if tick.ask is not None else None, "timestamp": tick.received_at.timestamp() if tick.received_at else float(tick.epoch), "epoch": tick.epoch}
        cache.set(cache_key, payload, 1)
        return payload


class MarketDataConsumer(AuthenticatedStateConsumer):
    resource = "market-data"


class PortfolioConsumer(AuthenticatedStateConsumer):
    resource = "portfolio"

    async def connect(self):
        await super().connect()
        self._broker_ws = None
        self._broker_task = None
        account = await self.selected_account()
        if not account:
            await self.send_json({"type": "portfolio.update", "status": "empty", "balance": None, "equity": None, "margin": None, "available_margin": None, "unrealized_pnl": None})
            return
        self.account_id = account.id
        self._account_type = account.broker.broker_type
        if account.broker.broker_type != "deriv":
            await self.send_json({"type": "portfolio.update", **await self.portfolio_state()})
            return
        try:
            await self._connect_deriv_stream(account)
        except Exception as exc:
            await self.mark_degraded(str(exc))
            await self.send_json({"type": "portfolio.error", "error": {"code": "BROKER_STREAM_FAILED", "message": "Live broker stream could not be established."}})
            await self.send_json({"type": "portfolio.update", **await self.portfolio_state()})

    async def disconnect(self, close_code):
        if self._broker_task:
            self._broker_task.cancel()
            try:
                await self._broker_task
            except asyncio.CancelledError:
                pass
        if self._broker_ws:
            try:
                await self._broker_ws.close()
            except Exception:
                pass
            self._broker_ws = None
        await super().disconnect(close_code)

    async def _connect_deriv_stream(self, account):
        from apps.brokers.services import BrokerRegistry

        adapter = BrokerRegistry().adapter(account.broker, account)
        url = await asyncio.to_thread(adapter._authenticated_ws_url)
        self._broker_ws = await websockets.connect(url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=10, max_size=2**20)
        await self._broker_ws.send(json.dumps({"balance": 1, "subscribe": 1, "req_id": 1001}))
        await self._broker_ws.send(json.dumps({"portfolio": 1, "req_id": 1002}))
        await self._broker_ws.send(json.dumps({"transaction": 1, "subscribe": 1, "req_id": 1003}))
        self._broker_task = asyncio.create_task(self._broker_loop())

    async def _broker_loop(self):
        while self._broker_ws:
            try:
                raw = await asyncio.wait_for(self._broker_ws.recv(), timeout=75)
                message = json.loads(raw)
            except asyncio.CancelledError:
                raise
            except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError):
                await self.mark_degraded("Broker websocket stopped responding")
                return
            if message.get("error"):
                await self.send_json({"type": "portfolio.error", "error": message["error"]})
                continue
            msg_type = message.get("msg_type")
            if msg_type == "balance":
                await self._handle_balance(message.get("balance") or {})
            elif msg_type == "portfolio":
                await self._handle_portfolio((message.get("portfolio") or {}).get("contracts") or [])
            elif msg_type == "transaction":
                await self._handle_transaction(message.get("transaction") or {})
                await self._send_portfolio_refresh()
            elif msg_type == "proposal_open_contract":
                await self._handle_contract(message.get("proposal_open_contract") or {})

    async def _send_portfolio_refresh(self):
        if self._broker_ws:
            await self._broker_ws.send(json.dumps({"portfolio": 1, "req_id": 2001}))

    async def _handle_balance(self, balance):
        value = balance.get("balance")
        currency = balance.get("currency")
        account_id = str(balance.get("loginid") or self.account_id)
        if value is None:
            return
        await self.update_account_realtime(account_id, value, currency, None, None)
        await self.send_json({"type": "account.balance", "account_id": account_id, "balance": value, "currency": currency, "timestamp": timezone.now().timestamp()})

    async def _handle_portfolio(self, contracts):
        total_profit = 0.0
        normalized = []
        for contract in contracts:
            try:
                profit = float(contract.get("profit") or 0)
            except (TypeError, ValueError):
                profit = 0.0
            total_profit += profit
            normalized.append({
                "contract_id": contract.get("contract_id"),
                "symbol": contract.get("underlying_symbol") or contract.get("symbol"),
                "contract_type": contract.get("contract_type"),
                "buy_price": contract.get("buy_price"),
                "bid_price": contract.get("bid_price"),
                "profit": contract.get("profit"),
                "status": contract.get("status"),
                "payout": contract.get("payout"),
            })
            contract_id = contract.get("contract_id")
            if contract_id and self._broker_ws:
                await self._broker_ws.send(json.dumps({"proposal_open_contract": 1, "contract_id": int(contract_id), "subscribe": 1}))
        await self.update_unrealized(total_profit)
        await self.send_json({"type": "portfolio.update", "status": "ready", "contracts": normalized, "unrealized_pnl": total_profit, "timestamp": timezone.now().timestamp()})

    async def _handle_contract(self, contract):
        if not contract:
            return
        try:
            profit = float(contract.get("profit") or 0)
        except (TypeError, ValueError):
            profit = 0.0
        await self.send_json({"type": "portfolio.contract", "contract": contract, "unrealized_pnl": profit, "timestamp": timezone.now().timestamp()})

    async def _handle_transaction(self, transaction):
        await self.send_json({"type": "account.transaction", "transaction": transaction, "timestamp": timezone.now().timestamp()})

    @database_sync_to_async
    def selected_account(self):
        from apps.brokers.models import BrokerAccount
        return BrokerAccount.objects.filter(user=self.scope["user"], status="active", broker__status="active").select_related("broker").order_by("-is_preferred", "-id").first()

    @database_sync_to_async
    def update_account_realtime(self, account_id, balance, currency, equity, available_margin):
        from apps.brokers.models import BrokerAccount, BrokerConnection
        account = BrokerAccount.objects.filter(pk=self.account_id, user=self.scope["user"]).first()
        if not account:
            return
        if account_id and str(account.account_id) != str(account_id):
            account.account_id = str(account_id)
        if balance is not None:
            account.balance = balance
        if currency:
            account.currency = str(currency)
        realtime = dict((account.credentials or {}).get("realtime") or {})
        if equity is not None:
            realtime["equity"] = equity
        if available_margin is not None:
            realtime["available_margin"] = available_margin
        realtime["last_stream_update"] = timezone.now().isoformat()
        credentials = dict(account.credentials or {})
        credentials["realtime"] = realtime
        account.credentials = credentials
        account.status = "active"
        account.last_synced_at = timezone.now()
        account.save(update_fields=["account_id", "balance", "currency", "credentials", "status", "last_synced_at"])
        BrokerConnection.objects.filter(broker_account=account).update(status="connected", last_ping=timezone.now(), updated_at=timezone.now())

    @database_sync_to_async
    def update_unrealized(self, unrealized_pnl):
        from apps.brokers.models import BrokerAccount, BrokerConnection
        account = BrokerAccount.objects.filter(pk=self.account_id, user=self.scope["user"]).first()
        if not account:
            return
        try:
            equity = float(account.balance) + float(unrealized_pnl)
        except (TypeError, ValueError):
            equity = None
        realtime = dict((account.credentials or {}).get("realtime") or {})
        realtime["unrealized_pnl"] = unrealized_pnl
        if equity is not None:
            realtime["equity"] = equity
        realtime["last_stream_update"] = timezone.now().isoformat()
        credentials = dict(account.credentials or {})
        credentials["realtime"] = realtime
        account.credentials = credentials
        if equity is not None:
            account.equity = equity
        account.last_synced_at = timezone.now()
        account.save(update_fields=["credentials", "equity", "last_synced_at"])
        BrokerConnection.objects.filter(broker_account=account).update(status="connected", last_ping=timezone.now(), updated_at=timezone.now())

    @database_sync_to_async
    def mark_degraded(self, message):
        from apps.brokers.models import BrokerConnection
        BrokerConnection.objects.filter(broker_account_id=getattr(self, "account_id", None)).update(status="degraded", heartbeat={"error": message}, updated_at=timezone.now())

    @database_sync_to_async
    def portfolio_state(self):
        from apps.portfolio.models import Portfolio
        portfolio = Portfolio.objects.filter(user=self.scope["user"], status="active").order_by("-updated_at").first()
        if not portfolio:
            return {"status": "empty", "balance": None, "equity": None, "margin": None, "available_margin": None, "unrealized_pnl": None}
        metadata = portfolio.metadata or {}
        return {"status": "ready", "balance": str(portfolio.current_balance), "equity": str(portfolio.equity), "margin": metadata.get("margin"), "available_margin": metadata.get("available_margin"), "unrealized_pnl": metadata.get("unrealized_pnl"), "currency": portfolio.currency, "timestamp": portfolio.updated_at.timestamp()}


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
        return [{"id": row.pk, "type": "notification", "severity": row.priority, "title": row.title, "message": row.message, "timestamp": row.created_at.timestamp(), "read": row.read_at is not None} for row in rows]
