"""Canonical broker -> AlgoBot realtime synchronization.

The service is intentionally broker-agnostic at its public boundary. Broker
adapters emit native WebSocket messages; this service normalizes the small set
of state changes that AlgoBot needs, persists authoritative account state, and
fans the same event to every connected UI consumer through Channels.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.db import close_old_connections
from django.utils import timezone

from .services import BrokerRegistry


class BrokerRealtimeSync:
    """Own one long-lived broker stream per account in a worker process."""

    def __init__(self, account):
        self.account_id = account.pk
        self.account = account
        self.broker = account.broker
        self.adapter = BrokerRegistry().adapter(self.broker, account)
        self.channel_layer = get_channel_layer()
        self._task = None
        self._market_tasks: list[asyncio.Task] = []

    @property
    def group_name(self) -> str:
        return f"algobot-user-{self.account.user_id}-broker"

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        if not self.account.is_connection_eligible:
            return
        if self.broker.broker_type != "deriv":
            return
        self._task = asyncio.create_task(self._run_account_stream())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for task in self._market_tasks:
            task.cancel()
        if self._market_tasks:
            await asyncio.gather(*self._market_tasks, return_exceptions=True)
            self._market_tasks.clear()

    async def _run_account_stream(self) -> None:
        subscriptions = [
            {"balance": 1, "subscribe": 1, "req_id": 1001},
            {"portfolio": 1, "req_id": 1002},
            {"transaction": 1, "subscribe": 1, "req_id": 1003},
        ]
        await self.adapter._stream(
            subscriptions,
            callback=self.handle_message,
            authenticated=True,
            stream_name=f"account:{self.account.account_id}",
        )

    async def handle_message(self, message: dict) -> None:
        """Normalize and persist one broker message before broadcasting it."""
        if not isinstance(message, dict):
            return
        msg_type = message.get("msg_type")
        if msg_type == "stream_status":
            await self._persist_connection_status(message)
            await self._broadcast("broker.connection", message)
            return
        if message.get("error"):
            await self._persist_connection_status({"status": "degraded", "error": message["error"]})
            await self._broadcast("broker.error", {"error": message["error"]})
            return
        if msg_type == "balance":
            payload = await self._sync_balance(message.get("balance") or {})
            await self._broadcast("account.balance", payload)
        elif msg_type == "portfolio":
            payload = await self._sync_portfolio(message.get("portfolio") or {})
            await self._broadcast("portfolio.update", payload)
        elif msg_type == "transaction":
            payload = self._normalize_transaction(message.get("transaction") or {})
            await self._broadcast("account.transaction", payload)
        elif msg_type == "proposal_open_contract":
            payload = self._normalize_contract(message.get("proposal_open_contract") or {})
            await self._broadcast("portfolio.contract", payload)
        elif msg_type == "tick":
            payload = await self._sync_tick(message.get("tick") or {})
            if payload:
                await self._broadcast("market.tick", payload)

    async def _broadcast(self, event_type: str, payload: dict) -> None:
        if not self.channel_layer:
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broker.event",
                "event_type": event_type,
                "payload": payload,
            },
        )

    @sync_to_async
    def _persist_connection_status(self, message: dict) -> None:
        close_old_connections()
        from .models import BrokerConnection

        status = str(message.get("status") or "connected")
        if status == "reconnecting":
            db_status = "degraded"
        elif status == "authentication_error":
            db_status = "error"
        elif status == "connected":
            db_status = "connected"
        else:
            db_status = status if status in {"connected", "disconnected", "degraded", "error"} else "degraded"
        BrokerConnection.objects.filter(broker_account_id=self.account_id).update(
            status=db_status,
            last_ping=timezone.now() if db_status == "connected" else None,
            heartbeat={"stream": message},
            updated_at=timezone.now(),
        )

    @sync_to_async
    def _sync_balance(self, balance: dict) -> dict:
        close_old_connections()
        from .models import BrokerAccount, BrokerConnection

        account = BrokerAccount.objects.select_related("broker").get(pk=self.account_id)
        account_id = str(balance.get("loginid") or balance.get("account_id") or account.account_id)
        raw_balance = balance.get("balance")
        currency = balance.get("currency")
        if raw_balance is not None:
            try:
                account.balance = Decimal(str(raw_balance))
            except (InvalidOperation, TypeError, ValueError):
                pass
        account.account_id = account_id
        if currency:
            account.currency = str(currency)
        realtime = dict((account.credentials or {}).get("realtime") or {})
        realtime.update({"balance": raw_balance, "currency": currency, "updated_at": timezone.now().isoformat()})
        credentials = dict(account.credentials or {})
        credentials["realtime"] = realtime
        account.credentials = credentials
        account.last_synced_at = timezone.now()
        account.status = "active"
        account.save(update_fields=["account_id", "balance", "currency", "credentials", "last_synced_at", "status"])
        BrokerConnection.objects.filter(broker_account=account).update(
            status="connected", last_ping=timezone.now(), updated_at=timezone.now()
        )
        return {
            "account_id": account_id,
            "balance": raw_balance,
            "currency": currency or account.currency,
            "timestamp": time.time(),
        }

    @sync_to_async
    def _sync_portfolio(self, portfolio: dict) -> dict:
        close_old_connections()
        from .models import BrokerAccount

        account = BrokerAccount.objects.get(pk=self.account_id)
        contracts = portfolio.get("contracts") or []
        normalized = []
        unrealized = Decimal("0")
        for contract in contracts:
            try:
                unrealized += Decimal(str(contract.get("profit") or 0))
            except (InvalidOperation, TypeError, ValueError):
                pass
            normalized.append(self._normalize_contract(contract))
        equity = account.balance + unrealized
        account.equity = equity
        realtime = dict((account.credentials or {}).get("realtime") or {})
        realtime.update({"unrealized_pnl": str(unrealized), "equity": str(equity), "updated_at": timezone.now().isoformat()})
        credentials = dict(account.credentials or {})
        credentials["realtime"] = realtime
        account.credentials = credentials
        account.last_synced_at = timezone.now()
        account.save(update_fields=["equity", "credentials", "last_synced_at"])
        return {
            "status": "ready",
            "account_id": account.account_id,
            "contracts": normalized,
            "unrealized_pnl": str(unrealized),
            "equity": str(equity),
            "balance": str(account.balance),
            "currency": account.currency,
            "timestamp": time.time(),
        }

    @staticmethod
    def _normalize_contract(contract: dict) -> dict:
        return {
            "contract_id": contract.get("contract_id"),
            "symbol": contract.get("underlying_symbol") or contract.get("symbol"),
            "contract_type": contract.get("contract_type"),
            "buy_price": contract.get("buy_price"),
            "bid_price": contract.get("bid_price"),
            "profit": contract.get("profit"),
            "status": contract.get("status") or contract.get("is_sold") and "closed" or "open",
            "payout": contract.get("payout"),
            "entry_spot": contract.get("entry_spot"),
            "current_spot": contract.get("current_spot"),
            "date_start": contract.get("date_start"),
            "date_expiry": contract.get("date_expiry"),
        }

    @staticmethod
    def _normalize_transaction(transaction: dict) -> dict:
        return {"transaction": transaction, "timestamp": time.time()}

    @staticmethod
    async def _sync_tick_async(tick: dict) -> dict | None:
        return None

    async def _sync_tick(self, tick: dict) -> dict | None:
        """Persist ticks through the existing market-data ingestion contract."""
        symbol = str(tick.get("symbol") or "").strip()
        quote = tick.get("quote")
        epoch = tick.get("epoch")
        if not symbol or quote is None or epoch is None:
            return None
        try:
            from apps.market_data.services import MarketDataService
            await sync_to_async(MarketDataService().tick_service.ingest)({
                "symbol": symbol,
                "quote": quote,
                "bid": tick.get("bid"),
                "ask": tick.get("ask"),
                "epoch": epoch,
                "volume": tick.get("volume", 0),
            })
        except Exception:
            # A persistence failure must never stop the broker stream. The
            # broker event remains authoritative and is still broadcast.
            pass
        return {
            "symbol": symbol,
            "price": quote,
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "epoch": epoch,
            "timestamp": time.time(),
        }


async def sync_active_deriv_accounts() -> None:
    """Run all active Deriv account streams until cancelled."""
    from .models import BrokerAccount

    accounts = await sync_to_async(list)(
        BrokerAccount.objects.select_related("broker").filter(
            broker__broker_type="deriv",
            broker__status="active",
            status="active",
        )
    )
    services = [BrokerRealtimeSync(account) for account in accounts if account.is_connection_eligible]
    await asyncio.gather(*(service.start() or asyncio.sleep(0) for service in services))
    await asyncio.gather(*(service._task for service in services if service._task), return_exceptions=False)
