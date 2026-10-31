"""Connected-broker market capabilities.

Deriv is the authoritative source for the market universe and contracts. Public
contract metadata is used for capability discovery because ``contracts_for``
is broker catalogue data and does not require an authenticated trading socket.
Actual order execution remains authenticated and broker/risk gated.
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from django.core.cache import cache
from django.db import close_old_connections
from rest_framework.decorators import api_view, permission_classes
from core.permissions import BrokerOnboardingRequired
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.account_context import get_active_account
from .deriv_sync import _request, sync_active_symbols
from .models import Candle, Tick
from .services import MarketDataService
from .constants import TIMEFRAMES

CATALOGUE_CACHE = "algobot:broker:deriv:active-symbols"
CAPABILITIES_CACHE_PREFIX = "algobot:broker:deriv:contracts-for:"
CAPABILITIES_STALE_PREFIX = "algobot:broker:deriv:contracts-for:stale:"
CAPABILITIES_CACHE_SECONDS = 300
CAPABILITIES_STALE_SECONDS = 86400
BACKTEST_TIMEFRAMES = ["tick", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]
_CATALOGUE_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="broker-catalogue-sync")
_CATALOGUE_SYNC_LOCK = threading.Lock()
_catalogue_sync_future = None


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
    return asyncio.run(asyncio.wait_for(_request(payload), timeout=6.0))


def _cached_database_catalogue():
    rows = MarketDataService.symbols.catalogue(
        broker="deriv", active=True, tradable=True
    )
    return [
        {
            "symbol": row.symbol,
            "display_name": row.display_name,
            "market": row.market,
            "sub_market": row.sub_market,
            "symbol_type": None,
            "pip_size": row.pip_size,
            "is_active": row.is_active,
            "is_tradable": row.is_tradable,
            # These live exchange fields are not persisted in MarketSymbol.
            # Never claim an exchange is open or unsuspended from a stale DB row.
            "exchange_is_open": None,
            "is_trading_suspended": None,
            "supported_timeframes": BACKTEST_TIMEFRAMES,
        }
        for row in rows
    ]
def _run_catalogue_sync():
    """Refresh the authoritative Deriv catalogue outside the request lifecycle."""
    close_old_connections()
    try:
        return sync_active_symbols()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("broker_catalogue_background_refresh_failed", exc_info=True)
        return 0
    finally:
        close_old_connections()


def _schedule_catalogue_sync():
    """Coalesce refreshes so slow Deriv responses never block catalogue requests."""
    global _catalogue_sync_future
    with _CATALOGUE_SYNC_LOCK:
        if _catalogue_sync_future is not None and not _catalogue_sync_future.done():
            return False
        _catalogue_sync_future = _CATALOGUE_SYNC_EXECUTOR.submit(_run_catalogue_sync)
        return True


def _catalogue_response(account, payload, *, stale=False, refreshing=False):
    payload = _with_available_timeframes(payload)
    return Response({
        "status": "refreshing" if refreshing and not payload else "stale" if stale else "ok",
        "source": "cached_broker_catalogue" if stale else "connected_broker",
        "broker": account.broker.name,
        "account_id": account.account_id,
        "symbols": payload,
        "count": len(payload),
        "supported_timeframes": BACKTEST_TIMEFRAMES,
        "stale": stale,
        "refreshing": refreshing,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, BrokerOnboardingRequired])
def catalogue(request):
    account = _account(request.user, request=request)
    if not account:
        return Response({"detail": "Connect a broker before loading its market catalogue."}, status=status.HTTP_409_CONFLICT)
    if account.broker.broker_type != "deriv":
        return Response({"detail": f"Live market catalogue is not implemented for {account.broker.name} yet."}, status=status.HTTP_409_CONFLICT)

    force_refresh = str(request.query_params.get("refresh") or "").lower() in {"1", "true", "yes"}
    try:
        payload = None if force_refresh else cache.get(CATALOGUE_CACHE)
    except Exception:
        payload = None

    if payload:
        return _catalogue_response(account, payload)

    # A persisted broker catalogue is immediately usable. A live refresh is
    # coalesced in the background when explicitly requested; never make a page
    # request wait on Deriv's public WebSocket.
    database_payload = _cached_database_catalogue()
    if database_payload and not force_refresh:
        try:
            cache.set(CATALOGUE_CACHE, database_payload, timeout=30)
        except Exception:
            pass
        return _catalogue_response(account, database_payload, stale=True)

    refreshing = _schedule_catalogue_sync()
    database_payload = _cached_database_catalogue()
    if database_payload:
        return _catalogue_response(account, database_payload, stale=True, refreshing=refreshing)

    return Response({
        "status": "refreshing",
        "code": "BROKER_CATALOGUE_REFRESHING",
        "detail": "The authoritative Deriv market catalogue is refreshing in the background. Retry shortly.",
        "source": "connected_broker",
        "broker": account.broker.name,
        "account_id": account.account_id,
        "symbols": [],
        "count": 0,
        "supported_timeframes": BACKTEST_TIMEFRAMES,
        "stale": False,
        "refreshing": True,
    }, status=status.HTTP_202_ACCEPTED)


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
