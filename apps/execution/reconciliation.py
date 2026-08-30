"""Reconcile broker execution truth into AlgoBot execution records.

This module deliberately treats broker identifiers and broker responses as
authoritative. A network timeout after a buy is an UNKNOWN state, never a
successful local trade.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone


EXECUTION_STATES = {"pending", "submitted", "open", "closed", "rejected", "unknown", "cancelled"}


def normalize_execution_event(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("proposal_open_contract") or payload.get("contract") or {}
    transaction_payload = payload.get("transaction") or {}
    contract_id = contract.get("contract_id") or payload.get("contract_id")
    transaction_id = (
        transaction_payload.get("transaction_id")
        or payload.get("transaction_id")
        or payload.get("buy_transaction_id")
    )
    status = str(contract.get("status") or payload.get("status") or "unknown").lower()
    if contract.get("is_sold") or contract.get("is_expired"):
        status = "closed"
    if status not in EXECUTION_STATES:
        status = "unknown"
    return {
        "broker_contract_id": str(contract_id) if contract_id is not None else None,
        "broker_transaction_id": str(transaction_id) if transaction_id is not None else None,
        "status": status,
        "symbol": contract.get("underlying_symbol") or contract.get("symbol") or payload.get("symbol"),
        "buy_price": contract.get("buy_price") or payload.get("buy_price"),
        "bid_price": contract.get("bid_price"),
        "profit": contract.get("profit"),
        "payout": contract.get("payout"),
        "entry_spot": contract.get("entry_spot"),
        "current_spot": contract.get("current_spot"),
        "expiry": contract.get("date_expiry") or contract.get("expiry_time"),
        "is_sold": bool(contract.get("is_sold")),
        "is_expired": bool(contract.get("is_expired")),
        "raw": payload,
        "received_at": timezone.now(),
    }


@transaction.atomic
def reconcile_execution_event(*, user, event: dict[str, Any]):
    """Upsert the broker event against an existing user-owned execution.

    The lookup intentionally requires an existing local execution. Broker
    events must never create an order for an unrelated user.
    """
    normalized = normalize_execution_event(event)
    contract_id = normalized["broker_contract_id"]
    transaction_id = normalized["broker_transaction_id"]
    if not contract_id and not transaction_id:
        return None

    from .models import Order

    query = Order.objects.filter(user=user)
    if contract_id:
        order = query.filter(broker_order_id=contract_id).first()
    else:
        order = query.filter(client_request_id=transaction_id).first()
    if not order:
        return None

    if contract_id:
        order.broker_order_id = contract_id
    if transaction_id:
        order.broker_transaction_id = transaction_id
    order.status = normalized["status"]
    if normalized["symbol"]:
        order.symbol = normalized["symbol"]
    for field, attr in (("buy_price", "entry_price"), ("bid_price", "exit_price"), ("profit", "profit_loss")):
        value = normalized.get(field)
        if value is None:
            continue
        try:
            setattr(order, attr, Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError):
            pass
    order.updated_at = timezone.now()
    order.save()
    return order
