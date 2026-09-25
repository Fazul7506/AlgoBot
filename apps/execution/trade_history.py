"""Broker-authoritative Trade History synchronization.

The broker is the only source of execution/settlement facts. Local rows are a
durable cache of broker observations, never a source for invented trades.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from apps.brokers.services import BrokerRegistry
from .models import BrokerTradeHistory


class TradeHistorySyncError(Exception):
    code = "trade_history_unavailable"
    retryable = True

    def __init__(self, message, *, code=None, retryable=None):
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


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
        else:
            status = "unknown"

    purchase_time = _epoch_datetime(_first(contract, "purchase_time", "date_start")) or _epoch_datetime(
        _first(tx, "transaction_time", "timestamp")
    )
    settlement_time = _epoch_datetime(_first(contract, "sell_time", "sell_spot_time", "exit_spot_time", "settlement_time"))
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
        "sell_price": _decimal(_first(contract, "sell_price", "sold_for")),
        "exit_price": _decimal(_first(contract, "exit_spot", "exit_price")),
        "stake": _decimal(_first(contract, "buy_price", "stake", "amount")),
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

    def _persist_normalized(self, normalized, now):
        """Persist broker-confirmed rows in a synchronous Django DB context."""
        with transaction.atomic():
            for row in normalized:
                contract_lookup = (
                    BrokerTradeHistory.objects.filter(
                        broker_account=self.account,
                        broker_contract_id=row["broker_contract_id"],
                    ).first()
                    if row["broker_contract_id"] else None
                )
                transaction_lookup = (
                    BrokerTradeHistory.objects.filter(
                        broker_account=self.account,
                        broker_transaction_id=row["broker_transaction_id"],
                    ).first()
                    if row["broker_transaction_id"] else None
                )

                if contract_lookup and transaction_lookup and contract_lookup.pk != transaction_lookup.pk:
                    raise TradeHistorySyncError(
                        "Deriv returned conflicting contract and transaction identifiers.",
                        code="BROKER_ID_CONFLICT",
                        retryable=False,
                    )

                existing = contract_lookup or transaction_lookup
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

    async def sync(self, *, limit=100, date_from=None, date_to=None):
        adapter = BrokerRegistry().adapter(self.account.broker, self.account)
        try:
            transactions = await adapter.get_trade_history(
                limit=min(max(int(limit or 100), 1), 100),
                date_from=date_from,
                date_to=date_to,
            )
        except (BrokerAuthenticationError, BrokerConnectionError):
            raise
        except BrokerOrderError as exc:
            raise TradeHistorySyncError(
                "Deriv rejected the Trade History request.",
                code="BROKER_HISTORY_REJECTED",
                retryable=False,
            ) from exc

        if not isinstance(transactions, list):
            raise TradeHistorySyncError(
                "Deriv returned an invalid Trade History payload.",
                code="BROKER_HISTORY_INVALID_PAYLOAD",
                retryable=True,
            )

        # The statement endpoint contains account transactions, not only trades.
        # Only rows carrying a broker contract ID are eligible for the trade ledger.
        # Deposits, withdrawals and other account transactions are deliberately ignored.
        grouped = {}
        for tx in transactions:
            if not isinstance(tx, dict):
                continue
            contract_id = tx.get("contract_id")
            if contract_id is None:
                continue
            key = str(contract_id)
            if key not in grouped:
                grouped[key] = tx

        partial = False
        contract_failures = 0
        normalized = []
        for tx in grouped.values():
            contract_id = tx.get("contract_id")
            try:
                contract = await self._contract(adapter, contract_id)
            except (BrokerAuthenticationError, BrokerConnectionError):
                raise
            except BrokerOrderError:
                partial = True
                contract_failures += 1
                continue
            except Exception:
                partial = True
                contract_failures += 1
                continue

            # A statement row alone is not enough to create a trade-history row.
            # Require Deriv's contract-level response before persisting execution facts.
            if not isinstance(contract, dict) or str(contract.get("contract_id") or "") != str(contract_id):
                partial = True
                contract_failures += 1
                continue

            row = normalize_deriv_trade(tx, contract)
            if not row["broker_contract_id"]:
                partial = True
                continue
            normalized.append(row)

        if grouped and not normalized:
            raise TradeHistorySyncError(
                "Deriv returned trade transactions, but no contract details could be confirmed.",
                code="BROKER_CONTRACT_DETAILS_UNAVAILABLE",
                retryable=True,
            )

        now = timezone.now()
        # Broker I/O is asynchronous, but Django ORM/transactions are synchronous.
        # Keep every database operation inside one sync boundary so this coroutine
        # never touches the ORM directly and cannot raise SynchronousOnlyOperation.
        await sync_to_async(self._persist_normalized, thread_sensitive=True)(normalized, now)
        return {
            "state": "partial" if partial else ("empty" if not normalized else "success"),
            "count": len(normalized),
            "contract_transactions": len(grouped),
            "contract_failures": contract_failures,
            "last_synced_at": now,
        }


def sync_deriv_trade_history(account, **filters):
    try:
        return asyncio.run(DerivTradeHistoryService(account).sync(**filters))
    except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError):
        raise
