"""Canonical broker -> AlgoBot realtime synchronization."""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.db import close_old_connections
from django.utils import timezone

from .services import async_broker_adapter

logger = logging.getLogger(__name__)


class BrokerRealtimeSync:
    """Own one long-lived broker stream per account in a worker process."""
    def __init__(self, account):
        self.account_id = account.pk
        self.account = account
        self.broker = account.broker
        self.adapter = None
        self.channel_layer = get_channel_layer()
        self._task = None

    @property
    def group_name(self):
        return f"algobot-user-{self.account.user_id}-broker"

    async def start(self):
        if self._task and not self._task.done():
            return
        if self.broker.broker_type != "deriv":
            return
        if self.adapter is None:
            self.adapter = await async_broker_adapter(self.account, self.broker)
        self._task = asyncio.create_task(self._run_account_stream())

    async def stop(self):
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_account_stream(self):
        subscriptions = [
            {"balance": 1, "subscribe": 1, "req_id": 1001},
            {"portfolio": 1, "req_id": 1002},
            {"transaction": 1, "subscribe": 1, "req_id": 1003},
            {"proposal_open_contract": 1, "subscribe": 1, "req_id": 1004},
        ]
        await self.adapter._stream(subscriptions, callback=self.handle_message, authenticated=True, stream_name=f"account:{self.account.account_id}")

    async def handle_message(self, message: dict):
        if not isinstance(message, dict):
            return
        msg_type = message.get("msg_type")
        if msg_type == "stream_status":
            await self._persist_connection_status(message)
            await self._broadcast("broker.connection", message)
            return
        if message.get("error"):
            await self._persist_connection_status({"status": "failed", "error": message["error"]})
            await self._broadcast("broker.error", {"error": message["error"]})
            return
        if msg_type == "balance":
            await self._broadcast("account.balance", await self._sync_balance(message.get("balance") or {}))
        elif msg_type == "portfolio":
            await self._broadcast("portfolio.update", await self._sync_portfolio(message.get("portfolio") or {}))
        elif msg_type == "transaction":
            await self._broadcast("account.transaction", self._normalize_transaction(message.get("transaction") or {}))
        elif msg_type == "proposal_open_contract":
            contract = message.get("proposal_open_contract") or {}
            await self._reconcile_execution(contract)
            await self._broadcast("portfolio.contract", self._normalize_contract(contract))
        elif msg_type == "tick":
            payload = await self._sync_tick(message.get("tick") or {})
            if payload:
                await self._broadcast("market.tick", payload)

    async def _reconcile_execution(self, contract: dict):
        try:
            from apps.execution.reconciliation import reconcile_execution_event
            await sync_to_async(reconcile_execution_event)(user=self.account.user, event={"proposal_open_contract": contract})
            from .position_sync import _persist_snapshot_sync, normalize_broker_position
            normalized = normalize_broker_position(contract)
            if normalized is not None:
                await sync_to_async(_persist_snapshot_sync, thread_sensitive=True)(self.account.pk, [normalized], full_snapshot=False)
        except Exception as exc:
            logger.exception(
                "Broker execution event reconciliation failed",
                extra={"account_id": self.account_id, "contract_id": contract.get("contract_id"), "error": str(exc)},
            )

    async def _broadcast(self, event_type, payload):
        if self.channel_layer:
            envelope = {
                "account_id": self.account_id,
                "broker_account_id": self.account.account_id,
                "payload": payload or {},
            }
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "broker.event", "event_type": event_type, "payload": envelope},
            )

    @sync_to_async
    def _persist_connection_status(self, message):
        close_old_connections()
        from .models import BrokerConnection
        status = str(message.get("status") or "connected")
        db_status = {"reconnecting": "degraded", "authentication_error": "failed", "connected": "connected", "failed": "failed"}.get(status, status if status in {"connected", "disconnected", "degraded", "failed", "reconnecting"} else "degraded")
        BrokerConnection.objects.filter(broker_account_id=self.account_id).update(status=db_status, last_ping=timezone.now() if db_status == "connected" else None, heartbeat={"stream": message}, updated_at=timezone.now())

    @sync_to_async
    def _sync_balance(self, balance):
        close_old_connections()
        from .models import BrokerAccount, BrokerConnection
        account = BrokerAccount.objects.select_related("broker").get(pk=self.account_id)
        account_id = str(balance.get("loginid") or balance.get("account_id") or account.account_id)
        raw_balance = balance.get("balance")
        currency = balance.get("currency")
        credentials = dict(account.credentials or {})
        realtime = dict(credentials.get("realtime") or {})
        existing_fields = credentials.get("financial_snapshot_fields")
        supplied = set(existing_fields) if isinstance(existing_fields, list) else set()
        update_fields = ["account_id", "credentials", "status"]
        snapshot_received = False

        if raw_balance is not None:
            try:
                parsed_balance = Decimal(str(raw_balance))
                if not parsed_balance.is_finite():
                    raise InvalidOperation
                account.balance = parsed_balance
                supplied.add("balance")
                realtime["balance"] = str(parsed_balance)
                update_fields.append("balance")
                snapshot_received = True
            except (InvalidOperation, TypeError, ValueError):
                logger.warning("Ignoring invalid broker balance", extra={"account_id": self.account_id})
        if currency:
            account.currency = str(currency)
            supplied.add("currency")
            realtime["currency"] = account.currency
            update_fields.append("currency")

        credentials["financial_snapshot_fields"] = sorted(supplied)
        realtime["updated_at"] = timezone.now().isoformat()
        credentials["realtime"] = realtime
        account.credentials = credentials
        account.account_id = account_id
        account.status = "active"
        if snapshot_received:
            account.last_synced_at = timezone.now()
            update_fields.append("last_synced_at")
        account.save(update_fields=update_fields)
        BrokerConnection.objects.filter(broker_account=account).update(status="connected", last_ping=timezone.now(), updated_at=timezone.now())
        return {"account_id": account_id, "balance": str(account.balance) if "balance" in supplied else None, "currency": account.currency if "currency" in supplied else None, "timestamp": time.time() if snapshot_received else None}

    @sync_to_async
    def _sync_portfolio(self, portfolio):
        close_old_connections()
        from .models import BrokerAccount
        from .position_sync import _persist_snapshot_sync, normalize_broker_position
        account = BrokerAccount.objects.select_related("broker").get(pk=self.account_id)
        contracts = portfolio.get("contracts")
        if not isinstance(contracts, list) or any(not isinstance(contract, dict) or contract.get("contract_id") in (None, "") for contract in contracts):
            logger.warning("Ignoring incomplete broker portfolio snapshot", extra={"account_id": self.account_id})
            return {"status": "unavailable", "account_id": account.account_id, "reason": "portfolio_contracts_missing"}
        normalized_records = [
            item for item in (normalize_broker_position(contract) for contract in contracts)
            if item is not None
        ]
        sync_meta = _persist_snapshot_sync(account.pk, normalized_records)
        normalized = [self._normalize_contract(contract) for contract in contracts if contract.get("contract_id") not in (None, "")]
        profit_values = [self._decimal_or_none(item.get("profit")) for item in normalized]
        unrealized = None
        if not contracts:
            # An authoritative empty portfolio means no open-contract P/L.
            unrealized = Decimal("0")
        elif profit_values and all(value is not None for value in profit_values):
            unrealized = sum(profit_values, Decimal("0"))
        credentials = dict(account.credentials or {})
        realtime = dict(credentials.get("realtime") or {})
        if unrealized is None:
            realtime.pop("unrealized_pnl", None)
        else:
            realtime["unrealized_pnl"] = str(unrealized)
        # Equity is not balance plus contract profit: only persist it when
        # the broker explicitly supplies an equity field elsewhere.
        realtime.pop("equity", None)
        realtime["updated_at"] = timezone.now().isoformat()
        credentials["realtime"] = realtime
        account.credentials = credentials
        account.save(update_fields=["credentials"])
        return {"status": "ready", "account_id": account.account_id, "contracts": normalized, "unrealized_pnl": str(unrealized) if unrealized is not None else None, "balance": str(account.balance) if "balance" in set(credentials.get("financial_snapshot_fields") or []) else None, "currency": account.currency if "currency" in set(credentials.get("financial_snapshot_fields") or []) else None, "sync": sync_meta, "timestamp": time.time()}

    @staticmethod
    def _decimal_or_none(value):
        if value in (None, ""):
            return None
        try:
            result = Decimal(str(value))
            return result if result.is_finite() else None
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_contract(contract):
        return {"contract_id": contract.get("contract_id"), "symbol": contract.get("underlying_symbol") or contract.get("symbol"), "contract_type": contract.get("contract_type"), "buy_price": contract.get("buy_price"), "bid_price": contract.get("bid_price"), "profit": contract.get("profit"), "status": contract.get("status") or ("closed" if contract.get("is_sold") else "open"), "payout": contract.get("payout"), "entry_spot": contract.get("entry_spot"), "current_spot": contract.get("current_spot"), "date_start": contract.get("date_start"), "date_expiry": contract.get("date_expiry"), "is_sold": contract.get("is_sold"), "is_expired": contract.get("is_expired"), "status_display": contract.get("status_display")}

    @staticmethod
    def _normalize_transaction(transaction):
        return {"transaction": transaction, "timestamp": time.time()}

    async def _sync_tick(self, tick):
        symbol = str(tick.get("symbol") or "").strip()
        quote = tick.get("quote")
        epoch = tick.get("epoch")
        if not symbol or quote is None or epoch is None:
            return None
        try:
            from apps.market_data.services import MarketDataService
            await sync_to_async(MarketDataService().tick_service.ingest)({"symbol": symbol, "quote": quote, "bid": tick.get("bid"), "ask": tick.get("ask"), "epoch": epoch, "volume": tick.get("volume", 0)})
        except Exception as exc:
            logger.exception(
                "Broker tick persistence failed",
                extra={"account_id": self.account_id, "symbol": symbol, "epoch": epoch, "error": str(exc)},
            )
            return None
        return {"symbol": symbol, "price": quote, "bid": tick.get("bid"), "ask": tick.get("ask"), "epoch": epoch, "timestamp": time.time()}


async def sync_active_deriv_accounts():
    from .models import BrokerAccount
    accounts = await sync_to_async(list)(BrokerAccount.objects.select_related("broker").filter(broker__broker_type="deriv", broker__status="active", status="active"))
    services = [BrokerRealtimeSync(account) for account in accounts]
    await asyncio.gather(*(service.start() for service in services))
    await asyncio.gather(*(service._task for service in services if service._task), return_exceptions=False)
