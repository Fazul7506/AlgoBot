"""Canonical broker-position synchronization and reconciliation.

The broker response is authoritative. Local rows are only a durable cache of
observed broker facts and never a source for manufacturing trading data.
"""
from __future__ import annotations

import asyncio

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from .exceptions import BrokerAuthenticationError, BrokerConnectionError


class PositionSyncError(RuntimeError):
    """Raised when the broker position snapshot cannot be obtained."""
    def __init__(self, message, *, code="BROKER_POSITION_SYNC_FAILED"):
        super().__init__(message)
        self.code = code


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _broker_datetime(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_broker_position(record: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    contract_id = record.get("contract_id")
    if contract_id in (None, ""):
        # A position without the broker's immutable identity cannot be safely
        # reconciled and must never receive a generated ID.
        return None

    contract_type = str(record.get("contract_type") or "").strip()
    status = str(record.get("status") or "").strip().lower()
    if record.get("is_sold"):
        status = "closed"
    elif record.get("is_expired"):
        status = "expired"
    elif not status:
        status = "open"

    buy_price = _decimal(record.get("buy_price"))
    current_price = _decimal(record.get("bid_price"))
    if current_price is None:
        current_price = _decimal(record.get("current_spot"))

    return {
        "contract_id": str(contract_id),
        "transaction_id": str(record.get("transaction_id")) if record.get("transaction_id") not in (None, "") else "",
        "broker_order_id": str(record.get("order_id")) if record.get("order_id") not in (None, "") else "",
        "symbol": str(record.get("underlying_symbol") or record.get("symbol") or ""),
        "display_name": str(record.get("display_name") or ""),
        "contract_type": contract_type,
        "direction": str(record.get("direction") or ""),
        "size": _decimal(record.get("amount") or record.get("quantity")),
        "stake": buy_price,
        "entry_price": buy_price,
        "current_price": current_price,
        "exit_price": _decimal(record.get("sell_spot") or record.get("exit_spot")),
        "payout": _decimal(record.get("payout")),
        "profit": _decimal(record.get("profit")),
        "currency": str(record.get("currency") or ""),
        "status": status,
        "opened_at": _broker_datetime(record.get("date_start") or record.get("purchase_time")),
        "expiry_time": _broker_datetime(record.get("date_expiry")),
        "closed_at": _broker_datetime(record.get("sell_spot_time") or record.get("exit_spot_time")),
        "settlement_time": _broker_datetime(record.get("settlement_time")),
        "broker_timestamp": _broker_datetime(record.get("date_start") or record.get("purchase_time")),
        "raw_data": record,
    }


@transaction.atomic
def _persist_snapshot_sync(account_id: int, normalized: list[dict[str, Any]], *, full_snapshot: bool = True) -> dict[str, Any]:
    from .models import BrokerAccount, Position

    account = BrokerAccount.objects.select_related("broker").get(pk=account_id)
    synced_at = timezone.now()
    broker_ids = set()

    for data in normalized:
        contract_id = data["contract_id"]
        broker_ids.add(contract_id)
        defaults = dict(data)
        defaults["last_synced_at"] = synced_at
        Position.objects.update_or_create(
            account=account,
            contract_id=contract_id,
            defaults={"broker": account.broker, **defaults},
        )

    if full_snapshot:
        # A complete broker portfolio snapshot is authoritative for which
        # contracts are currently open. A contract absent from that snapshot
        # is no longer open, but its final lifecycle/result must not be
        # fabricated. Keep the row for historical reconciliation while leaving
        # exit/profit/settlement fields unknown until the broker supplies them.
        stale = Position.objects.filter(
            account=account,
            status__in=["open", "active", "pending"],
        ).exclude(contract_id="")
        if broker_ids:
            stale = stale.exclude(contract_id__in=broker_ids)
        stale.update(status="unknown", last_synced_at=synced_at)

    return {
        "status": "ready",
        "account_id": account.pk,
        "broker_account_id": account.account_id,
        "currency": account.currency,
        "count": len(normalized),
        "synchronized_at": synced_at.isoformat(),
    }


class BrokerPositionSyncService:
    """Fetch and reconcile one authenticated broker account."""

    async def synchronize(self, account):
        from .services import BrokerRegistry
        from .models import Position

        if not account or not account.is_connection_eligible:
            raise PositionSyncError("The selected broker account is not connected and ready.")

        adapter = BrokerRegistry().adapter(account.broker, account)
        try:
            records = await adapter.get_positions()
        except BrokerAuthenticationError as exc:
            raise PositionSyncError("The broker session is no longer authorized.", code="BROKER_AUTHENTICATION_FAILED") from exc
        except BrokerConnectionError as exc:
            raise PositionSyncError("The broker did not provide an authoritative position snapshot.", code="BROKER_UNAVAILABLE") from exc
        except Exception as exc:
            raise PositionSyncError("The broker did not provide an authoritative position snapshot.") from exc

        if not isinstance(records, list):
            raise PositionSyncError("The broker returned an invalid position snapshot.")

        normalized = [item for item in (normalize_broker_position(r) for r in records) if item is not None]
        current_ids = {item["contract_id"] for item in normalized}
        stale_ids = await sync_to_async(list, thread_sensitive=True)(
            Position.objects.filter(account_id=account.pk, status__in=["open", "active", "pending"]).exclude(contract_id="").exclude(contract_id__in=current_ids).values_list("contract_id", flat=True)
        ) if current_ids else await sync_to_async(list, thread_sensitive=True)(
            Position.objects.filter(account_id=account.pk, status__in=["open", "active", "pending"]).exclude(contract_id="").values_list("contract_id", flat=True)
        )
        if stale_ids:
            async def fetch_final(contract_id):
                try:
                    return await adapter.get_trade_contract(contract_id)
                except (BrokerAuthenticationError, BrokerConnectionError):
                    raise
                except NotImplementedError:
                    return None
                except Exception:
                    return None
            try:
                final_records = await asyncio.gather(*(fetch_final(cid) for cid in stale_ids))
            except BrokerAuthenticationError as exc:
                raise PositionSyncError("The broker session is no longer authorized.", code="BROKER_AUTHENTICATION_FAILED") from exc
            except BrokerConnectionError as exc:
                raise PositionSyncError("The broker connection failed while reconciling stale contracts.", code="BROKER_UNAVAILABLE") from exc
            normalized.extend(item for item in (normalize_broker_position(r) for r in final_records if isinstance(r, dict)) if item is not None)

        sync_meta = await sync_to_async(_persist_snapshot_sync, thread_sensitive=True)(account.pk, normalized)
        return {
            "positions": normalized,
            "meta": sync_meta,
        }

    async def synchronize_closed(self, account, limit=100):
        from .services import BrokerRegistry

        if not account or not account.is_connection_eligible:
            raise PositionSyncError("The selected broker account is not connected and ready.")

        adapter = BrokerRegistry().adapter(account.broker, account)
        try:
            history = await adapter.get_trade_history(limit=max(1, min(int(limit), 100)))
        except BrokerAuthenticationError as exc:
            raise PositionSyncError("The broker session is no longer authorized.", code="BROKER_AUTHENTICATION_FAILED") from exc
        except BrokerConnectionError as exc:
            raise PositionSyncError("The broker did not provide authoritative trade history.", code="BROKER_UNAVAILABLE") from exc
        except Exception as exc:
            raise PositionSyncError("The broker did not provide authoritative trade history.") from exc

        if not isinstance(history, list):
            raise PositionSyncError("The broker returned an invalid trade-history response.")

        contract_ids = []
        seen = set()
        for row in history:
            if not isinstance(row, dict):
                continue
            contract_id = row.get("contract_id")
            if contract_id in (None, ""):
                continue
            key = str(contract_id)
            if key not in seen:
                seen.add(key)
                contract_ids.append(key)

        async def fetch_final(contract_id):
            try:
                return await adapter.get_trade_contract(contract_id)
            except (BrokerAuthenticationError, BrokerConnectionError):
                raise
            except NotImplementedError:
                return None
            except Exception:
                return None

        try:
            records = await asyncio.gather(*(fetch_final(cid) for cid in contract_ids))
        except BrokerAuthenticationError as exc:
            raise PositionSyncError("The broker session is no longer authorized.", code="BROKER_AUTHENTICATION_FAILED") from exc
        except BrokerConnectionError as exc:
            raise PositionSyncError("The broker connection failed while retrieving closed contracts.", code="BROKER_UNAVAILABLE") from exc

        normalized = [
            item for item in (normalize_broker_position(record) for record in records if isinstance(record, dict))
            if item is not None and item.get("status") in {"closed", "expired", "settled", "won", "lost"}
        ]
        meta = await sync_to_async(_persist_snapshot_sync, thread_sensitive=True)(
            account.pk, normalized, full_snapshot=False
        )
        meta["history_count"] = len(history)
        return {"positions": normalized, "meta": meta}

    async def synchronize_contract(self, account, contract):
        normalized = normalize_broker_position(contract)
        if normalized is None:
            raise PositionSyncError("The broker contract did not contain a stable contract ID.")
        meta = await sync_to_async(_persist_snapshot_sync, thread_sensitive=True)(
            account.pk, [normalized], full_snapshot=False
        )
        return {"position": normalized, "meta": meta}
