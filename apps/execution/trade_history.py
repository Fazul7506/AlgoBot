"""Broker-authoritative Trade History synchronization.

The broker is the only source of execution/settlement facts. Local rows are a
durable cache of broker observations, never a source for invented trades.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from apps.brokers.services import BrokerRegistry
from .models import BrokerTradeHistory


class TradeHistorySyncError(Exception):
    code = "trade_history_unavailable"


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _epoch_datetime(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _first(data, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_deriv_trade(transaction_data, contract=None):
    tx = transaction_data if isinstance(transaction_data, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    contract_id = _first(contract, "contract_id") or _first(tx, "contract_id")
    transaction_id = _first(tx, "transaction_id", "buy_transaction_id") or _first(contract, "transaction_id")
    symbol = _first(contract, "underlying_symbol", "symbol") or _first(tx, "symbol", "underlying_symbol")
    status = _first(contract, "status", "status_display")
    if not status:
        if contract.get("is_sold"):
            status = "sold"
        elif contract.get("is_expired"):
            status = "expired"
        elif contract_id:
            status = "open"
        else:
            status = "transaction"

    purchase_time = _epoch_datetime(_first(contract, "purchase_time", "date_start")) or _epoch_datetime(
        _first(tx, "transaction_time", "timestamp")
    )
    settlement_time = _epoch_datetime(_first(contract, "sell_time", "settlement_time"))
    expiry_time = _epoch_datetime(_first(contract, "date_expiry", "expiry_time"))
    broker_timestamp = _epoch_datetime(_first(tx, "transaction_time", "timestamp")) or purchase_time

    return {
        "broker_contract_id": str(contract_id) if contract_id is not None else None,
        "broker_transaction_id": str(transaction_id) if transaction_id is not None else None,
        "broker_order_id": str(_first(tx, "order_id") or _first(contract, "order_id")) if (_first(tx, "order_id") or _first(contract, "order_id")) is not None else None,
        "reference_id": str(_first(tx, "reference_id", "reference")) if _first(tx, "reference_id", "reference") is not None else None,
        "symbol": symbol,
        "display_name": _first(contract, "display_name") or symbol,
        "instrument_type": _first(contract, "contract_category", "instrument_type"),
        "contract_type": _first(contract, "contract_type", "contract_type_name", "shortcode"),
        "direction": _first(contract, "direction") or _first(tx, "action"),
        "duration": _decimal(_first(contract, "duration")),
        "duration_unit": _first(contract, "duration_unit"),
        "barrier": _first(contract, "barrier", "barrier_spot"),
        "buy_price": _decimal(_first(contract, "buy_price", "purchase_price")),
        "entry_price": _decimal(_first(contract, "entry_spot", "entry_price")),
        "sell_price": _decimal(_first(contract, "sell_price")),
        "exit_price": _decimal(_first(contract, "exit_spot", "exit_price")),
        "stake": _decimal(_first(contract, "buy_price", "stake", "amount") or _first(tx, "amount")),
        "payout": _decimal(_first(contract, "payout")),
        "profit_loss": _decimal(_first(contract, "profit", "profit_loss")),
        "currency": _first(contract, "currency") or _first(tx, "currency"),
        "status": str(status).lower(),
        "purchase_time": purchase_time,
        "execution_time": _epoch_datetime(_first(contract, "date_start", "purchase_time")) or purchase_time,
        "settlement_time": settlement_time,
        "expiry_time": expiry_time,
        "broker_timestamp": broker_timestamp,
        "raw_data": {"transaction": tx, "contract": contract},
    }


class DerivTradeHistoryService:
    def __init__(self, account):
        self.account = account
        if account.broker.broker_type != "deriv":
            raise TradeHistorySyncError("This Trade History implementation requires a connected Deriv account.")

    async def _contract(self, adapter, contract_id):
        if not contract_id:
            return {}
        return await adapter.get_trade_contract(contract_id)

    async def sync(self, *, limit=100, date_from=None, date_to=None):
        adapter = BrokerRegistry().adapter(self.account.broker, self.account)
        transactions = await adapter.get_trade_history(
            limit=min(max(int(limit or 100), 1), 100),
            date_from=date_from,
            date_to=date_to,
        )
        if not isinstance(transactions, list):
            raise TradeHistorySyncError("Deriv returned an invalid trade-history payload.")

        grouped = {}
        for tx in transactions:
            if not isinstance(tx, dict):
                continue
            contract_id = tx.get("contract_id")
            key = str(contract_id) if contract_id is not None else f"tx:{tx.get('transaction_id')}"
            if key not in grouped:
                grouped[key] = tx

        partial = False
        normalized = []
        for tx in grouped.values():
            contract = {}
            contract_id = tx.get("contract_id")
            if contract_id is not None:
                try:
                    contract = await self._contract(adapter, contract_id)
                except (BrokerAuthenticationError, BrokerConnectionError):
                    raise
                except Exception:
                    partial = True
            row = normalize_deriv_trade(tx, contract)
            if not row["broker_contract_id"] and not row["broker_transaction_id"]:
                continue
            normalized.append(row)

        now = timezone.now()
        with transaction.atomic():
            for row in normalized:
                lookup = (
                    {"broker_account": self.account, "broker_contract_id": row["broker_contract_id"]}
                    if row["broker_contract_id"]
                    else {"broker_account": self.account, "broker_transaction_id": row["broker_transaction_id"]}
                )
                existing = BrokerTradeHistory.objects.filter(**lookup).first()
                if existing:
                    for key, value in row.items():
                        setattr(existing, key, value)
                    existing.user_id = self.account.user_id
                    existing.last_synced_at = now
                    existing.save()
                else:
                    BrokerTradeHistory.objects.create(
                        user_id=self.account.user_id,
                        broker_account=self.account,
                        last_synced_at=now,
                        **row,
                    )

        self.account.last_synced_at = now
        self.account.save(update_fields=["last_synced_at"])
        return {"state": "partial" if partial else "success", "count": len(normalized), "last_synced_at": now}


def sync_deriv_trade_history(account, **filters):
    try:
        return asyncio.run(DerivTradeHistoryService(account).sync(**filters))
    except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError):
        raise
