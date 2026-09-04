"""Connected-broker market capabilities.

Deriv is the authoritative source for the market universe and contracts. Public
contract metadata is used for capability discovery because ``contracts_for``
is broker catalogue data and does not require an authenticated trading socket.
Actual order execution remains authenticated and broker/risk gated.
"""
from __future__ import annotations

import asyncio

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.brokers.models import BrokerAccount
from .deriv_sync import _request

CATALOGUE_CACHE = "algobot:broker:deriv:active-symbols"
CAPABILITIES_CACHE_PREFIX = "algobot:broker:deriv:contracts-for:"


def _account(user):
    return (
        BrokerAccount.objects.filter(user=user, status="active", broker__status="active")
        .select_related("broker")
        .order_by("-id")
        .first()
    )


def _public_deriv(payload):
    return asyncio.run(_request(payload))


def _normalise_symbol(item):
    symbol = str(item.get("underlying_symbol") or "").strip()
    return {
        "symbol": symbol,
        "display_name": str(item.get("underlying_symbol_name") or symbol),
        "market": str(item.get("market") or ""),
        "sub_market": str(item.get("submarket") or item.get("subgroup") or ""),
        "symbol_type": str(item.get("underlying_symbol_type") or ""),
        "pip_size": item.get("pip_size"),
        "is_active": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
        "is_tradable": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
        "exchange_is_open": bool(item.get("exchange_is_open", True)),
        "is_trading_suspended": bool(item.get("is_trading_suspended", False)),
        "trade_count": item.get("trade_count"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def catalogue(request):
    account = _account(request.user)
    if not account:
        return Response({"detail": "Connect a broker before loading its market catalogue."}, status=status.HTTP_409_CONFLICT)
    if account.broker.broker_type != "deriv":
        return Response({"detail": f"Live market catalogue is not implemented for {account.broker.name} yet."}, status=status.HTTP_409_CONFLICT)
    try:
        payload = cache.get(CATALOGUE_CACHE)
        if payload is None:
            response = _public_deriv({"active_symbols": "brief"})
            raw = response.get("active_symbols") or []
            payload = [_normalise_symbol(item) for item in raw if isinstance(item, dict) and item.get("underlying_symbol")]
            payload = [item for item in payload if item["is_active"]]
            cache.set(CATALOGUE_CACHE, payload, timeout=30)
        if not payload:
            raise RuntimeError("Deriv returned no active tradable instruments")
        return Response({"status":"ok","source":"connected_broker","broker":account.broker.name,"account_id":account.account_id,"symbols":payload,"count":len(payload),"stale":False})
    except Exception as exc:
        return Response({"status":"error","code":"BROKER_CATALOGUE_UNAVAILABLE","detail":str(exc),"source":"connected_broker"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def capabilities(request):
    """Return fast broker-authoritative contract capabilities for the selected symbol.

    Capability discovery is deliberately decoupled from authenticated execution:
    Deriv's public ``contracts_for`` response is sufficient to populate the
    terminal selector. This avoids the extra OAuth/OTP WebSocket handshake that
    previously caused the UI to sit on "Loading broker contracts…" until the
    frontend timeout expired.
    """
    symbol = str(request.query_params.get("symbol") or "").strip()
    account = _account(request.user)
    if not account:
        return Response({"detail": "Connect a broker before loading trading capabilities."}, status=status.HTTP_409_CONFLICT)
    if not symbol:
        return Response({"detail": "symbol is required"}, status=status.HTTP_400_BAD_REQUEST)
    if account.broker.broker_type != "deriv":
        return Response({"detail": f"Broker contract capabilities are not implemented for {account.broker.name} yet."}, status=status.HTTP_409_CONFLICT)

    cache_key = f"{CAPABILITIES_CACHE_PREFIX}{symbol}"
    try:
        payload = cache.get(cache_key)
        if payload is None:
            response = _public_deriv({"contracts_for": symbol})
            root = response.get("contracts_for") or {}
            raw_contracts = root.get("available") or []
            if not isinstance(raw_contracts, list):
                raise RuntimeError("Broker returned an invalid contract capability payload")
            unique = {}
            for item in raw_contracts:
                if not isinstance(item, dict) or not item.get("contract_type"):
                    continue
                contract_type = str(item.get("contract_type")).strip().upper()
                unique.setdefault(contract_type, {
                    "contract_type": contract_type,
                    "contract_category": str(item.get("contract_category") or ""),
                    "expiry_type": str(item.get("expiry_type") or ""),
                    "barriers": item.get("barriers", 0),
                    "market": str(item.get("market") or ""),
                    "submarket": str(item.get("submarket") or ""),
                    "sentiment": str(item.get("sentiment") or ""),
                    "underlying_symbol": str(item.get("underlying_symbol") or symbol),
                })
            contracts = list(unique.values())
            payload = {
                "symbol": symbol,
                "contracts": contracts,
                "contract_types": sorted(unique),
                "trade_types": sorted({c["contract_category"] for c in contracts if c["contract_category"]}),
                "timeframe_capability": {"granularity": "broker_defined_integer_seconds", "minimum_seconds": 1},
            }
            cache.set(cache_key, payload, timeout=30)
        if not payload.get("contracts"):
            return Response({"detail": "Deriv reports no contracts for this instrument.", "symbol": symbol}, status=status.HTTP_409_CONFLICT)
        return Response({"status":"ok","source":"connected_broker","broker":account.broker.name,"account_id":account.account_id,**payload})
    except Exception as exc:
        return Response({"status":"error","code":"BROKER_CAPABILITIES_UNAVAILABLE","detail":str(exc),"source":"connected_broker","symbol":symbol}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
