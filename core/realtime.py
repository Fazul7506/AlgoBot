from __future__ import annotations

import asyncio
import json

import websockets
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone


class AuthenticatedStateConsumer(AsyncJsonWebsocketConsumer):
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
            try: await self._poll_task
            except asyncio.CancelledError: pass

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "subscribe" and self.resource == "market-data":
            symbol = str(content.get("symbol") or "").strip()
            if not symbol or len(symbol) > 40 or not await self.symbol_exists(symbol):
                await self.send_json({"type": "error", "error": {"code": "UNKNOWN_SYMBOL", "message": "The requested market symbol is not available."}}); return
            self.symbol = symbol
            if self._poll_task: self._poll_task.cancel()
            self._poll_task = asyncio.create_task(self._market_loop())
            await self.send_json({"type": "market.subscription", "symbol": symbol, "status": "subscribed"}); return
        if action == "unsubscribe":
            self.symbol = None
            if self._poll_task:
                self._poll_task.cancel(); self._poll_task = None
            await self.send_json({"type": "subscription", "status": "unsubscribed"}); return
        if action == "ping":
            await self.send_json({"type": "pong", "timestamp": timezone.now().timestamp()}); return
        await self.send_json({"type": "error", "error": {"code": "UNSUPPORTED_ACTION", "message": "Unsupported websocket action."}})

    async def _market_loop(self):
        last_epoch = None
        while self.symbol:
            tick = await self.live_tick(self.symbol)
            if tick and tick["epoch"] != last_epoch:
                last_epoch = tick["epoch"]; await self.send_json({"type": "market.tick", **tick})
            await asyncio.sleep(1)

    @database_sync_to_async
    def symbol_exists(self, symbol):
        from apps.market_data.models import MarketSymbol
        return MarketSymbol.objects.filter(symbol=symbol, is_active=True).exists()

    @database_sync_to_async
    def live_tick(self, symbol):
        from apps.brokers.models import BrokerAccount
        from apps.brokers.services import BrokerRegistry
        from apps.market_data.deriv_sync import fetch_tick
        from apps.market_data.services import MarketDataService
        from apps.market_data.models import Tick
        account = BrokerAccount.objects.filter(user=self.scope["user"], status="active", broker__status="active", is_preferred=True).select_related("broker").first()
        if not account: return None
        cache_key = f"algobot:realtime:broker-quote:{account.pk}:{account.broker.broker_type}:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None: return cached
        try:
            if account.broker.broker_type == "deriv": data = fetch_tick(symbol)
            else: data = asyncio.run(asyncio.wait_for(BrokerRegistry().adapter(account.broker, account).get_market_data(symbol), timeout=7))
            tick = MarketDataService().tick_service.ingest({"symbol": symbol, "quote": data.get("price", data.get("quote")), "bid": data.get("bid"), "ask": data.get("ask"), "epoch": data.get("epoch"), "volume": data.get("volume", 0)})
        except Exception:
            tick = Tick.objects.filter(symbol__symbol=symbol).select_related("symbol").order_by("-epoch", "-id").first()
        if not tick: return None
        payload = {"symbol": symbol, "price": float(tick.quote), "bid": float(tick.bid) if tick.bid is not None else None, "ask": float(tick.ask) if tick.ask is not None else None, "timestamp": tick.received_at.timestamp() if tick.received_at else float(tick.epoch), "epoch": tick.epoch, "account_id": account.id, "broker_account_id": account.account_id}
        cache.set(cache_key, payload, 1); return payload


class MarketDataConsumer(AuthenticatedStateConsumer): resource = "market-data"


class PortfolioConsumer(AuthenticatedStateConsumer):
    resource = "portfolio"

    async def connect(self):
        await super().connect()
        self._broker_ws = None; self._broker_task = None; self.account_id = None; self._stream_generation = 0
        account = await self.selected_account()
        if not account:
            await self.send_json({"type": "portfolio.update", "status": "empty", "balance": None, "equity": None, "margin": None, "available_margin": None, "unrealized_pnl": None}); return
        self.account_id = account.id; self._account_type = account.broker.broker_type
        await self._announce_account(account)
        if account.broker.broker_type != "deriv":
            await self.send_json({"type": "portfolio.update", **await self.portfolio_state()}); return
        try: await self._connect_deriv_stream(account)
        except Exception as exc:
            await self.mark_degraded(str(exc)); await self.send_json({"type": "portfolio.error", "error": {"code": "BROKER_STREAM_FAILED", "message": "Live broker stream could not be established."}}); await self.send_json({"type": "portfolio.update", **await self.portfolio_state()})

    async def receive_json(self, content, **kwargs):
        if content.get("action") == "account.switch":
            try: requested_id = int(content.get("account_id"))
            except (TypeError, ValueError):
                await self.send_json({"type": "account.switch.rejected", "error": {"code": "ACCOUNT_REQUIRED", "message": "A valid account_id is required."}}); return
            account = await self.get_account(requested_id)
            if not account or not account.is_preferred:
                await self.send_json({"type": "account.switch.rejected", "error": {"code": "ACCOUNT_NOT_ACTIVE", "message": "The requested account is not the authoritative active account."}}); return
            await self._switch_broker_stream(account); return
        await super().receive_json(content, **kwargs)

    async def _switch_broker_stream(self, account):
        old_id = self.account_id
        await self._close_broker_stream()
        self._stream_generation += 1
        generation = self._stream_generation
        self.account_id = account.id; self._account_type = account.broker.broker_type
        await self.send_json({"type": "account.switching", "previous_account_id": old_id, "active_account_id": account.id, "broker_account_id": account.account_id})
        await self._announce_account(account)
        try:
            if account.broker.broker_type == "deriv": await self._connect_deriv_stream(account, generation)
            else: await self.send_json({"type": "portfolio.update", **await self.portfolio_state()})
            if generation != self._stream_generation: return
            await self.send_json({"type": "account.switched", "active_account_id": account.id, "broker_account_id": account.account_id, "account_type": (account.credentials or {}).get("account_type")})
        except asyncio.CancelledError: raise
        except Exception as exc:
            await self.mark_degraded(str(exc)); await self.send_json({"type": "account.switch.failed", "active_account_id": account.id, "error": {"code": "BROKER_STREAM_FAILED", "message": "The new account was selected, but its live broker stream could not be established."}})

    async def _announce_account(self, account):
        await self.send_json({"type": "account.context", "active_account_id": account.id, "broker_account_id": account.account_id, "account_type": (account.credentials or {}).get("account_type"), "currency": account.currency, "balance": str(account.balance) if account.balance is not None else None})

    async def _close_broker_stream(self):
        if self._broker_task:
            task = self._broker_task; self._broker_task = None; task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        if self._broker_ws:
            ws = self._broker_ws; self._broker_ws = None
            try: await ws.close()
            except Exception: pass

    async def disconnect(self, close_code):
        await self._close_broker_stream(); await super().disconnect(close_code)

    async def _connect_deriv_stream(self, account, generation=None):
        from apps.brokers.services import BrokerRegistry
        adapter = BrokerRegistry().adapter(account.broker, account)
        url = await asyncio.to_thread(adapter._authenticated_ws_url)
        ws = await websockets.connect(url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=10, max_size=2**20)
        if generation is not None and generation != self._stream_generation:
            await ws.close(); return
        self._broker_ws = ws
        await ws.send(json.dumps({"balance": 1, "subscribe": 1, "req_id": 1001}))
        await ws.send(json.dumps({"portfolio": 1, "req_id": 1002}))
        await ws.send(json.dumps({"transaction": 1, "subscribe": 1, "req_id": 1003}))
        self._broker_task = asyncio.create_task(self._broker_loop(ws, self.account_id, self._stream_generation))

    async def _broker_loop(self, ws, account_id, generation):
        while self._broker_ws is ws and self.account_id == account_id and self._stream_generation == generation:
            try: message = json.loads(await asyncio.wait_for(ws.recv(), timeout=75))
            except asyncio.CancelledError: raise
            except Exception:
                if self._broker_ws is ws: await self.mark_degraded("Broker websocket stopped responding")
                return
            if self._broker_ws is not ws or self.account_id != account_id or self._stream_generation != generation: return
            if message.get("error"): await self.send_json({"type": "portfolio.error", "error": message["error"], "active_account_id": account_id}); continue
            msg_type = message.get("msg_type")
            if msg_type == "balance": await self._handle_balance(message.get("balance") or {}, account_id, generation)
            elif msg_type == "portfolio": await self._handle_portfolio((message.get("portfolio") or {}).get("contracts") or [], account_id, generation)
            elif msg_type == "transaction": await self._handle_transaction(message.get("transaction") or {}, account_id, generation); await self._send_portfolio_refresh(ws, account_id, generation)
            elif msg_type == "proposal_open_contract": await self._handle_contract(message.get("proposal_open_contract") or {}, account_id, generation)

    async def _send_portfolio_refresh(self, ws, account_id, generation):
        if self._broker_ws is ws and self.account_id == account_id and self._stream_generation == generation: await ws.send(json.dumps({"portfolio": 1, "req_id": 2001}))

    async def _handle_balance(self, balance, account_id, generation):
        value = balance.get("balance"); broker_login = str(balance.get("loginid") or "")
        if value is None or self._broker_ws is None or self.account_id != account_id or self._stream_generation != generation: return
        if broker_login and not await self.is_current_broker_account(broker_login): return
        currency = balance.get("currency")
        await self.update_account_realtime(account_id, value, currency, None, None)
        await self.send_json({"type": "account.balance", "account_id": account_id, "broker_account_id": broker_login or None, "balance": value, "currency": currency, "timestamp": timezone.now().timestamp()})

    async def _handle_portfolio(self, contracts, account_id, generation):
        if self.account_id != account_id or self._stream_generation != generation: return
        total_profit = 0.0; normalized = []
        for contract in contracts:
            try: profit = float(contract.get("profit") or 0)
            except (TypeError, ValueError): profit = 0.0
            total_profit += profit
            normalized.append({"contract_id": contract.get("contract_id"), "symbol": contract.get("underlying_symbol") or contract.get("symbol"), "contract_type": contract.get("contract_type"), "buy_price": contract.get("buy_price"), "bid_price": contract.get("bid_price"), "profit": contract.get("profit"), "status": contract.get("status"), "payout": contract.get("payout")})
        await self.update_unrealized(total_profit)
        await self.send_json({"type": "portfolio.update", "status": "ready", "contracts": normalized, "unrealized_pnl": total_profit, "active_account_id": account_id, "timestamp": timezone.now().timestamp()})

    async def _handle_contract(self, contract, account_id, generation):
        if contract and self.account_id == account_id and self._stream_generation == generation: await self.send_json({"type": "portfolio.contract", "contract": contract, "active_account_id": account_id, "timestamp": timezone.now().timestamp()})

    async def _handle_transaction(self, transaction, account_id, generation):
        if self.account_id == account_id and self._stream_generation == generation: await self.send_json({"type": "account.transaction", "transaction": transaction, "active_account_id": account_id, "timestamp": timezone.now().timestamp()})

    @database_sync_to_async
    def selected_account(self):
        from apps.brokers.models import BrokerAccount
        return BrokerAccount.objects.filter(user=self.scope["user"], status="active", broker__status="active", is_preferred=True).select_related("broker").first()

    @database_sync_to_async
    def get_account(self, account_id):
        from apps.brokers.models import BrokerAccount
        return BrokerAccount.objects.filter(pk=account_id, user=self.scope["user"], status="active", broker__status="active").select_related("broker").first()

    @database_sync_to_async
    def is_current_broker_account(self, broker_account_id):
        from apps.brokers.models import BrokerAccount
        return BrokerAccount.objects.filter(pk=self.account_id, user=self.scope["user"], account_id=str(broker_account_id), is_preferred=True, status="active").exists()

    @database_sync_to_async
    def update_account_realtime(self, account_id, balance, currency, equity, available_margin):
        from apps.brokers.models import BrokerAccount, BrokerConnection
        account = BrokerAccount.objects.filter(pk=self.account_id, user=self.scope["user"], is_preferred=True, status="active").first()
        if not account or account.id != account_id: return
        if balance is not None: account.balance = balance
        if currency: account.currency = str(currency)
        realtime = dict((account.credentials or {}).get("realtime") or {}); realtime["last_stream_update"] = timezone.now().isoformat()
        if equity is not None: realtime["equity"] = equity
        if available_margin is not None: realtime["available_margin"] = available_margin
        credentials = dict(account.credentials or {}); credentials["realtime"] = realtime; account.credentials = credentials; account.last_synced_at = timezone.now()
        account.save(update_fields=["balance", "currency", "credentials", "last_synced_at"])
        BrokerConnection.objects.filter(broker_account=account).update(status="connected", last_ping=timezone.now(), updated_at=timezone.now())

    @database_sync_to_async
    def update_unrealized(self, unrealized_pnl):
        from apps.brokers.models import BrokerAccount, BrokerConnection
        account = BrokerAccount.objects.filter(pk=self.account_id, user=self.scope["user"], is_preferred=True, status="active").first()
        if not account: return
        try: equity = float(account.balance) + float(unrealized_pnl)
        except (TypeError, ValueError): equity = None
        realtime = dict((account.credentials or {}).get("realtime") or {}); realtime["unrealized_pnl"] = unrealized_pnl; realtime["last_stream_update"] = timezone.now().isoformat()
        if equity is not None: realtime["equity"] = equity; account.equity = equity
        credentials = dict(account.credentials or {}); credentials["realtime"] = realtime; account.credentials = credentials; account.last_synced_at = timezone.now()
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
        if not portfolio: return {"status": "empty", "balance": None, "equity": None, "margin": None, "available_margin": None, "unrealized_pnl": None}
        metadata = portfolio.metadata or {}
        return {"status": "ready", "balance": str(portfolio.current_balance), "equity": str(portfolio.equity), "margin": metadata.get("margin"), "available_margin": metadata.get("available_margin"), "unrealized_pnl": metadata.get("unrealized_pnl"), "currency": portfolio.currency, "timestamp": portfolio.updated_at.timestamp()}


class NotificationConsumer(AuthenticatedStateConsumer):
    resource = "notifications"
    async def connect(self):
        await super().connect()
        await self.send_json({"type": "notification.snapshot", "notifications": await self.latest_notifications()})
    @database_sync_to_async
    def latest_notifications(self):
        from apps.notifications.models import Notification
        rows = Notification.objects.filter(user=self.scope["user"]).order_by("-created_at")[:20]
        return [{"id": row.pk, "type": "notification", "severity": row.priority, "title": row.title, "message": row.message, "timestamp": row.created_at.timestamp(), "read": row.read_at is not None} for row in rows]
