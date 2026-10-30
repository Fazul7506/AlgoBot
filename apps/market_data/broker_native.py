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
from core.permissions import BrokerOnboardingRequired
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.account_context import get_active_account
from .deriv_sync import _request, sync_active_symbols
from .models import Candle, MarketSymbol, Tick
from .constants import TIMEFRAMES

CATALOGUE_CACHE = "algobot:broker:deriv:active-symbols"
CAPABILITIES_CACHE_PREFIX = "algobot:broker:deriv:contracts-for:"
CAPABILITIES_STALE_PREFIX = "algobot:broker:deriv:contracts-for:stale:"
CAPABILITIES_CACHE_SECONDS = 300
CAPABILITIES_STALE_SECONDS = 86400
BACKTEST_TIMEFRAMES = ["tick", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]


def _with_available_timeframes(items):
    """Attach per-instrument intervals that actually exist in persisted history."""
    symbols = [str(item.get("symbol") or "").strip().upper() for item in items]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        return items
    available = {symbol: set() for symbol in symbols}
    for row in Candle.objects.filter(symbol__symbol__in=symbols).values("symbol__symbol", "timeframe").distinct():
        available.setdefault(row["symbol__symbol"], set()).add(row["timeframe"])
    for symbol in Tick.objects.filter(symbol__symbol__in=symbols).values_list("symbol__symbol", flat=True).distinct():
        available.setdefault(symbol, set()).add("tick")
    order = {value: index for index, value in enumerate(BACKTEST_TIMEFRAMES)}
    for item in items:
        symbol = str(item.get("symbol") or "").strip().upper()
        item["available_timeframes"] = sorted(available.get(symbol, set()), key=lambda value: order.get(value, len(order)))
    return items


def _account(user, request=None):
    return get_active_account(user, request=request)


def _public_deriv(payload):
    return asyncio.run(_request(payload))


def _normalise_symbol(item):
    """Normalise current and legacy Deriv active_symbols payloads consistently."""
    symbol = str(
        item.get("underlying_symbol") or item.get("symbol") or item.get("code") or ""
    ).strip()
    return {
        "symbol": symbol,
        "display_name": str(
            item.get("underlying_symbol_name")
            or item.get("display_name")
            or item.get("name")
            or symbol
        ).strip(),
        "market": str(item.get("market") or item.get("market_name") or "").strip(),
        "sub_market": str(
            item.get("submarket") or item.get("sub_market") or item.get("subgroup") or ""
        ).strip(),
        "symbol_type": str(
            item.get("underlying_symbol_type") or item.get("symbol_type") or ""
        ).strip(),
        "pip_size": item.get("pip_size"),
        "is_active": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
        "is_tradable": bool(item.get("exchange_is_open", True)) and not bool(item.get("is_trading_suspended", False)),
        "exchange_is_open": bool(item.get("exchange_is_open", True)),
        "is_trading_suspended": bool(item.get("is_trading_suspended", False)),
        "trade_count": item.get("trade_count"),
        "supported_timeframes": BACKTEST_TIMEFRAMES,
    }


def _cached_database_catalogue():
    rows = MarketSymbol.objects.filter(
        broker="deriv", is_active=True, is_tradable=True
    ).order_by("market", "symbol")
    return _with_available_timeframes([
        {
            "symbol": row.symbol,
            "display_name": row.display_name,
            "market": row.market,
            "sub_market": row.sub_market,
            "symbol_type": "",
            "pip_size": row.pip_size,
            "is_active": row.is_active,
            "is_tradable": row.is_tradable,
            "exchange_is_open": True,
            "is_trading_suspended": False,
            "supported_timeframes": BACKTEST_TIMEFRAMES,
        }
        for row in rows
    ])
def _catalogue_response(account, payload, *, stale=False):
    payload = _with_available_timeframes(payload)
    return Response({
        "status": "stale" if stale else "ok",
        "source": "cached_broker_catalogue" if stale else "connected_broker",
        "broker": account.broker.name,
        "account_id": account.account_id,
        "symbols": payload,
        "count": len(payload),
        "supported_timeframes": BACKTEST_TIMEFRAMES,
        "stale": stale,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, BrokerOnboardingRequired])
def catalogue(request):
    account = _account(request.user, request=request)
    if not account:
        return Response({"detail": "Connect a broker before loading its market catalogue."}, status=status.HTTP_409_CONFLICT)
    if account.broker.broker_type != "deriv":
        return Response({"detail": f"Live market catalogue is not implemented for {account.broker.name} yet."}, status=status.HTTP_409_CONFLICT)
    try:
        force_refresh = str(request.query_params.get("refresh") or "").lower() in {"1", "true", "yes"}
        payload = None if force_refresh else cache.get(CATALOGUE_CACHE)
        if payload:
            return _catalogue_response(account, payload)

        # Prefer the durable broker catalogue before making a network request.
        # This keeps every workspace responsive when the public Deriv socket is
        # slow or temporarily unavailable; the response is explicitly marked
        # stale and the user can request a live refresh.
        if not force_refresh:
            database_payload = _cached_database_catalogue()
            if database_payload:
                cache.set(CATALOGUE_CACHE, database_payload, timeout=30)
                return _catalogue_response(account, database_payload, stale=True)

        if force_refresh:
            # sync_active_symbols already performs the authoritative
            # active_symbols request and persists it. Do not immediately issue
            # a second identical WebSocket request after syncing.
            sync_active_symbols()
            payload = _cached_database_catalogue()
            if not payload:
                raise RuntimeError("Deriv returned no active tradable instruments")
            cache.set(CATALOGUE_CACHE, payload, timeout=30)
            return _catalogue_response(account, payload)

        # A brand-new database with no synced symbols gets one bounded public
        # request. Subsequent workspaces share the cache/database result above.
        response = _public_deriv({"active_symbols": "brief"})
        raw = response.get("active_symbols") or []
        payload = [_normalise_symbol(item) for item in raw if isinstance(item, dict) and item.get("underlying_symbol")]
        payload = [item for item in payload if item["is_active"]]
        if not payload:
            raise RuntimeError("Deriv returned no active tradable instruments")
        cache.set(CATALOGUE_CACHE, payload, timeout=30)
        return _catalogue_response(account, payload)
    except Exception as exc:
        cached = _cached_database_catalogue()
        if cached:
            return _catalogue_response(account, cached, stale=True)
        return Response({"status":"error","code":"BROKER_CATALOGUE_UNAVAILABLE","detail":str(exc),"source":"connected_broker"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@permission_classes([IsAuthenticated, BrokerOnboardingRequired])
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
        return Response({"status":"ok","source":"connected_broker","broker":account.broker.name,"account_id":account.account_id,**payload})
    except Exception as exc:
        try:
            stale = cache.get(f"{CAPABILITIES_STALE_PREFIX}{symbol}")
        except Exception as cache_exc:
            # Redis may reject even reads under maxmemory; never let that mask
            # the original provider failure or turn this endpoint into HTTP 500.
            stale = None
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
