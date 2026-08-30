"""Reconcile broker execution truth into AlgoBot execution records."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

EXECUTION_STATES = {"pending", "submitted", "open", "closed", "rejected", "unknown", "cancelled"}


def normalize_execution_event(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("proposal_open_contract") or payload.get("contract") or {}
    tx = payload.get("transaction") or {}
    contract_id = contract.get("contract_id") or payload.get("contract_id")
    transaction_id = tx.get("transaction_id") or payload.get("transaction_id") or payload.get("buy_transaction_id")
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
        "raw": payload,
        "received_at": timezone.now(),
    }


@transaction.atomic
def reconcile_execution_event(*, user, event: dict[str, Any]):
    """Reconcile only an existing user-owned Order; never invent a trade."""
    normalized = normalize_execution_event(event)
    contract_id = normalized["broker_contract_id"]
    transaction_id = normalized["broker_transaction_id"]
    if not contract_id and not transaction_id:
        return None

    from .models import Order
    from . import constants as c

    query = Order.objects.filter(user=user)
    order = None
    if contract_id:
        order = query.filter(broker_reference=contract_id).first()
    if not order and transaction_id:
        order = query.filter(client_request_id=transaction_id).first()
    if not order:
        # Do not attach an unknown broker execution to a local order. The
        # caller can surface the event for reconciliation/recovery instead.
        return None

    order.broker_reference = contract_id or order.broker_reference
    order.broker_response = normalized["raw"]
    if normalized["symbol"]:
        order.symbol = normalized["symbol"]
    broker_status = normalized["status"]
    status_map = {
        "open": c.ORDER_STATUS_EXECUTED,
        "closed": c.ORDER_STATUS_ARCHIVED,
        "cancelled": c.ORDER_STATUS_CANCELLED,
        "rejected": c.ORDER_STATUS_FAILED,
        "unknown": c.ORDER_STATUS_SENT,
    }
    order.status = status_map.get(broker_status, order.status)
    if normalized["buy_price"] is not None:
        try:
            order.price = Decimal(str(normalized["buy_price"]))
        except (InvalidOperation, TypeError, ValueError):
            pass
    order.save(update_fields=["broker_reference", "broker_response", "symbol", "status", "price", "updated_at"])
    return order
