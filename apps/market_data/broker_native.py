"""Connected-broker market capabilities.

Deriv is the authoritative source for the market universe and contracts. Public
contract metadata is used for capability discovery because ``contracts_for``
is broker catalogue data and does not require an authenticated trading socket.
Actual order execution remains authenticated and broker/risk gated.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.account_context import get_active_account
from .deriv_sync import _request
from .models import MarketSymbol

CATALOGUE_CACHE = "algobot:broker:deriv:active-symbols"
CAPABILITIES_CACHE_PREFIX = "algobot:broker:deriv:contracts-for:"
CAPABILITIES_STALE_PREFIX = "algobot:broker:deriv:contracts-for:stale:"
CAPABILITIES_CACHE_SECONDS = 300
CAPABILITIES_STALE_SECONDS = 86400


def _account(user, request=None):
    if not getattr(user, "is_authenticated", False):
        return None
    return get_active_account(user, request=request)


def _public_deriv(payload):
    return asyncio.run(_request(payload))


def _market_label(value, sub_market=""):
    raw = str(value or "").strip().lower().replace("-", "_")
    sub = str(sub_market or "").strip().lower()
    if raw in {"synthetic_index", "synthetic_indices", "derived", "derived_indices", "basket_index", "basket_indices"}:
        if "boom" in sub:
            return "Boom"
        if "crash" in sub:
            return "Crash"
        if "jump" in sub:
            return "Jump Indices"
        if "volatility" in sub or "random" in sub:
            return "Volatility Indices"
        return "Derived Indices"
    if raw in {"forex", "forex_indices"}:
        return "Forex"
    if raw in {"cryptocurrency", "crypto"}:
        return "Crypto"
    if raw in {"commodities", "commodity"}:
        return "Commodities"
    if raw in {"indices", "stock_index", "stock_indices"}:
        return "Stock Indices"
    if raw in {"jump", "jump_indices"}:
        return "Jump Indices"
    if raw in {"boom", "boom_indices"}:
        return "Boom"
    if raw in {"crash", "crash_indices"}:
        return "Crash"
    return "Derived Indices"


def _normalise_symbol(item):
    symbol = str(item.get("underlying_symbol") or "").strip()
    suspended = bool(item.get("is_trading_suspended", False))
    exchange_open = bool(item.get("exchange_is_open", True))
    pip_size = item.get("pip_size")
    try:
        pip_size = max(0, min(12, int(pip_size))) if pip_size is not None else 2
    except (TypeError, ValueError):
        pip_size = 2
    sub_market = str(item.get("submarket") or item.get("subgroup") or "")
    return {
        "symbol": symbol,
        "display_name": str(item.get("underlying_symbol_name") or symbol),
        "market": str(item.get("market") or ""),
        "sub_market": sub_market,
        "market_label": _market_label(item.get("market"), sub_market),
        "symbol_type": str(item.get("underlying_symbol_type") or ""),
        "pip_size": pip_size,
        # A market can remain in the catalogue while its exchange is closed.
        # ``is_active`` means the broker still publishes the instrument;
        # ``is_tradable`` carries the current exchange-open state.
        "is_active": not suspended,
        "is_tradable": exchange_open and not suspended,
        "exchange_is_open": exchange_open,
        "is_trading_suspended": suspended,
        "trade_count": item.get("trade_count"),
    }


def _persist_catalogue(payload):
    """Persist the last broker-authoritative catalogue for outage recovery."""
    rows = []
    for item in payload:
        symbol = str(item.get("symbol") or "").strip()
        if not symbol or len(symbol) > 40:
            continue
        rows.append(
            MarketSymbol(
                symbol=symbol,
                broker="deriv",
                display_name=str(item.get("display_name") or symbol)[:160],
                market=str(item.get("market_label") or _market_label(item.get("market")))[:80],
                sub_market=str(item.get("sub_market") or "")[:120],
                pip_size=int(item.get("pip_size") or 2),
                tick_size=Decimal("0"),
                is_active=bool(item.get("is_active", True)),
                is_tradable=bool(item.get("is_tradable", True)),
            )
        )
    if not rows:
        return 0
    with transaction.atomic():
        MarketSymbol.objects.bulk_create(
            rows,
            update_conflicts=True,
            update_fields=[
                "broker",
                "display_name",
                "market",
                "sub_market",
                "pip_size",
                "tick_size",
                "is_active",
                "is_tradable",
            ],
            unique_fields=["symbol"],
            batch_size=500,
        )
    return len(rows)


def _cached_database_catalogue():
    rows = MarketSymbol.objects.filter(
        broker="deriv", is_active=True
    ).order_by("market", "symbol")
    return [
        {
            "symbol": row.symbol,
            "display_name": row.display_name,
            "market": row.market,
            "sub_market": row.sub_market,
            "symbol_type": "",
            "pip_size": row.pip_size,
            "is_active": row.is_active,
            "is_tradable": row.is_tradable,
            "exchange_is_open": row.is_tradable,
            "is_trading_suspended": False,
        }
        for row in rows
    ]


@api_view(["GET"])
@permission_classes([AllowAny])
def catalogue(request):
    """Return the public Deriv instrument catalogue.

    Instrument discovery is public broker metadata and must not depend on a
    selected account. Account authentication remains required for execution,
    account data, and private broker capabilities. This prevents the Markets
    and Trading pages from showing an outage merely because account context is
    temporarily unavailable.
    """
    account = _account(getattr(request, "user", None), request=request)
    try:
        payload = cache.get(CATALOGUE_CACHE)
        if payload is None:
            response = _public_deriv({"active_symbols": "brief"})
            raw = response.get("active_symbols") or []
            if not isinstance(raw, list):
                raise RuntimeError("Deriv returned an invalid active_symbols payload")
            payload = [
                _normalise_symbol(item)
                for item in raw
                if isinstance(item, dict) and item.get("underlying_symbol")
            ]
            payload = [item for item in payload if item["is_active"]]
            if payload:
                cache.set(CATALOGUE_CACHE, payload, timeout=30)
                try:
                    _persist_catalogue(payload)
                except Exception:
                    # Database persistence is an outage-recovery enhancement;
                    # a healthy live broker response must not fail because the
                    # cache database is temporarily read-only/unavailable.
                    pass
        if payload:
            return Response({
                "status": "ok",
                "source": "connected_broker_catalogue" if account else "public_broker_catalogue",
                "broker": account.broker.name if account else "Deriv",
                "account_id": account.account_id if account else None,
                "symbols": payload,
                "count": len(payload),
                "stale": False,
            })
        raise RuntimeError("Deriv returned no active broker instruments")
    except Exception as exc:
        cached = _cached_database_catalogue()
        if cached:
            return Response({
                "status": "stale",
                "source": "cached_broker_catalogue",
                "broker": account.broker.name if account else "Deriv",
                "account_id": account.account_id if account else None,
                "symbols": cached,
                "count": len(cached),
                "stale": True,
                "detail": "Live broker catalogue refresh is temporarily unavailable; serving the last known broker catalogue.",
            })
        return Response({
            "status": "error",
            "code": "BROKER_CATALOGUE_UNAVAILABLE",
            "detail": "The broker market catalogue is temporarily unavailable.",
            "source": "connected_broker" if account else "public_broker_catalogue",
            "error_type": exc.__class__.__name__,
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def capabilities(request):
    """Return fast broker-authoritative contract capabilities for the selected symbol."""
    symbol = str(request.query_params.get("symbol") or "").strip()
    account = _account(request.user, request=request)
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
            cache.set(cache_key, payload, timeout=CAPABILITIES_CACHE_SECONDS)
            cache.set(f"{CAPABILITIES_STALE_PREFIX}{symbol}", payload, timeout=CAPABILITIES_STALE_SECONDS)
        if not payload.get("contracts"):
            return Response({"detail": "Deriv reports no contracts for this instrument.", "symbol": symbol}, status=status.HTTP_409_CONFLICT)
        return Response({"status":"ok","source":"connected_broker","broker": account.broker.name,"account_id":account.account_id,**payload})
    except Exception as exc:
        stale = cache.get(f"{CAPABILITIES_STALE_PREFIX}{symbol}")
        if isinstance(stale, dict) and stale.get("contracts"):
            return Response({
                "status": "stale",
                "code": "BROKER_CAPABILITIES_STALE",
                "detail": "Live broker capability refresh is temporarily unavailable; serving the last verified broker contract catalogue.",
                "source": "cached_broker_capabilities",
                "broker": account.broker.name,
                "account_id": account.account_id,
                "stale": True,
                **stale,
            })
        return Response({"status":"error","code":"BROKER_CAPABILITIES_UNAVAILABLE","detail":str(exc),"source":"connected_broker","symbol":symbol}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
