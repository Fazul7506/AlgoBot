from __future__ import annotations

import asyncio
import hashlib
import json
import time
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse

from apps.analysis.advanced import analyze_candles
from apps.analytics.broker_intelligence import build_account_risk_context
from apps.brokers.services import SynchronizationService
from core.account_context import get_active_account
from apps.market_data.models import MarketSnapshot, MarketSymbol
from apps.market_data.deriv_sync import fetch_contracts_for, fetch_tick
from apps.market_data.historical import fetch_and_store, fetch_and_store_ticks
from apps.market_data.constants import TIMEFRAMES
from apps.market_data.research_data import ResearchDataService


ANALYTICS_CACHE_SECONDS = 15
ANALYSIS_CACHE_SECONDS = 3


def _broker_trade_spec(result, market, capabilities, account_context=None):
    """Build a complete analysis specification from broker capabilities + verified candles.

    Broker-supplied contract metadata is never invented. Strategy fields are
    explicitly deterministic labels derived from the same broker OHLC analysis
    already returned by this endpoint, so the UI never presents an empty
    strategy row as if a broker field were missing.
    """
    caps = capabilities or {}
    contract_types = [str(v) for v in caps.get("available_contract_types", []) if v]
    families = [str(v) for v in caps.get("available_contract_families", []) if v]
    expiry = [str(v) for v in caps.get("expiry_types", []) if v]
    sentiments = [str(v) for v in caps.get("sentiments", []) if v]
    signal = str(result.get("signal") or "Neutral")
    regime = str(result.get("volatility_regime") or "normal")
    factors = [str(v) for v in result.get("factors") or [] if v]
    structure = str(result.get("structure") or "Range")
    direction = "BUY" if "Bullish" in signal else "SELL" if "Bearish" in signal else "HOLD"
    strategy_parts = []
    for factor in factors:
        if factor not in strategy_parts:
            strategy_parts.append(factor)
    if structure not in strategy_parts:
        strategy_parts.append(structure)
    strategy = " + ".join(strategy_parts[:5]) or "Broker OHLC technical analysis"
    category = "Technical analysis · broker OHLC confluence"
    risk_profile = f"{regime.title()} volatility · confidence-gated"
    execution_mode = "Manual command · execution gate enforced"
    entry = f"{direction} only when {signal} baseline is confirmed by the live Deriv quote"
    confirmation = " + ".join(["Deriv live tick", *factors[:3]]) if factors else "Deriv live tick + broker OHLC analysis"
    contract_type = " / ".join(contract_types) or "Broker contract catalogue"
    contract_family = " / ".join(families) or "Broker contract categories"
    duration = None
    return {
        "market_type": market.market,
        "sub_market": market.sub_market or "Broker active-symbol submarket",
        "instrument": market.display_name,
        "trade_type": f"{signal} analysis baseline",
        "direction": direction,
        "contract_type": contract_type,
        "contract_family": contract_family,
        "duration": duration,
        "duration_unit": None,
        "barrier": None,
        "stake": account_context.get("recommended_stake") if account_context else None,
        "risk_budget": account_context.get("risk_budget") if account_context else None,
        "payout": None,
        "strategy": strategy,
        "strategy_category": category,
        "risk_profile": risk_profile,
        "account_type": account_context.get("account_type") if account_context else None,
        "account_balance": account_context.get("balance") if account_context else None,
        "free_margin": account_context.get("free_margin") if account_context else None,
        "execution_mode": execution_mode,
        "entry_condition": entry,
        "confirmation": confirmation,
        "market_regime": regime,
        "quote_source": "Deriv public market-data WebSocket",
        "broker_contract_sentiments": " / ".join(sentiments) or None,
        "broker_expiry_types": " / ".join(expiry) or None,
        "source": "Deriv contracts_for + Deriv OHLC/tick analysis",
    }



@login_required
def analysis_data(request):
    symbol = (request.GET.get("symbol") or "R_100").strip().upper()
    timeframe = (request.GET.get("timeframe") or "1m").strip()
    try:
        limit = min(max(int(request.GET.get("limit", 300)), 50), 1000)
    except (TypeError, ValueError):
        limit = 300

    refresh_requested = str(request.GET.get("refresh", "1")).lower() in {"1", "true", "yes"}
    active_account = get_active_account(request.user, request=request)
    cache_key = "algobot:analysis:v5:" + hashlib.sha256(
        json.dumps([
            request.user.pk,
            active_account.pk if active_account else None,
            symbol,
            timeframe.lower(),
            limit,
            bool(refresh_requested),
        ]).encode("utf-8")
    ).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    research_data = ResearchDataService()
    try:
        canonical_timeframe = research_data.timeframe(timeframe)
        market = research_data.market(symbol)
    except ValueError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=404)

    refresh_result = None
    if refresh_requested:
        try:
            if canonical_timeframe == "tick" or TIMEFRAMES[canonical_timeframe] < 60:
                refresh_result = fetch_and_store_ticks(market.symbol, count=min(max(limit, 50), 1000))
            else:
                refresh_result = fetch_and_store(market.symbol, canonical_timeframe, count=min(max(limit, 50), 1000))
            live_tick = fetch_tick(market.symbol)
            from apps.market_data.services import MarketDataService
            MarketDataService().tick_service.ingest(live_tick)
        except Exception as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "code": "BROKER_DATA_REFRESH_FAILED",
                    "message": "Fresh Deriv market data could not be confirmed; stale research data was not substituted.",
                    "detail": str(exc),
                    "symbol": market.symbol,
                    "timeframe": canonical_timeframe,
                },
                status=503,
            )

    candles = research_data.candles(market.symbol, canonical_timeframe, limit=limit)

    if not candles:
        return JsonResponse(
            {
                "status": "error",
                "message": "No persisted market candles are available for this symbol/timeframe.",
                "source": "market_data.Candle",
                "symbol": market.symbol,
                "timeframe": canonical_timeframe,
            },
            status=503,
        )

    result = analyze_candles(candles, symbol=market.symbol, timeframe=canonical_timeframe)
    try:
        broker_capabilities = fetch_contracts_for(market.symbol)
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "code": "BROKER_CONTRACT_DATA_FAILED",
            "message": "Deriv contract capabilities could not be confirmed for this analysis.",
            "detail": str(exc),
            "symbol": market.symbol,
            "timeframe": canonical_timeframe,
        }, status=503)
    account_context = None
    if active_account is not None:
        try:
            if refresh_requested:
                synced_account, _broker_data = asyncio.run(
                    asyncio.wait_for(
                        SynchronizationService().sync_account(active_account),
                        timeout=8.0,
                    )
                )
                active_account = synced_account
            account_context = build_account_risk_context(
                request.user,
                active_account,
                signal=result.get("signal"),
                confidence=result.get("confidence"),
                volatility=result.get("volatility_regime"),
            )
        except Exception as exc:
            if refresh_requested:
                return JsonResponse(
                    {
                        "status": "error",
                        "code": "BROKER_ACCOUNT_CONTEXT_FAILED",
                        "message": "The selected broker account could not be refreshed, so account-dependent risk and sizing values were not substituted.",
                        "detail": str(exc),
                    },
                    status=503,
                )
    result["account_context"] = account_context
    result["trade_spec"] = _broker_trade_spec(
        result, market, broker_capabilities, account_context
    )
    result["contract_capabilities"] = broker_capabilities
    snapshot = MarketSnapshot.objects.filter(symbol=market).only("last_price", "bid", "ask", "change_percent").first()
    if refresh_requested:
        # The live broker tick is the authoritative current price. The stored
        # snapshot remains useful for bid/ask/change context, but must never
        # override the current broker quote in Analysis.
        try:
            live_tick
        except UnboundLocalError:
            live_tick = None
        if live_tick and live_tick.get("quote") is not None:
            result["price"] = float(live_tick["quote"])
    result["snapshot"] = (
        {
            "last_price": float(snapshot.last_price),
            "bid": float(snapshot.bid) if snapshot.bid is not None else None,
            "ask": float(snapshot.ask) if snapshot.ask is not None else None,
            "change_percent": float(snapshot.change_percent),
        }
        if snapshot
        else None
    )
    latest_epoch = int(candles[-1]["epoch"])
    age_seconds = max(0, int(time.time()) - latest_epoch)
    result["data_provenance"] = {
        "source": "market_data.Candle",
        "broker": "Deriv",
        "storage": "database",
        "refresh_requested": refresh_requested,
        "refresh_result": refresh_result,
        "symbol": market.symbol,
        "timeframe": canonical_timeframe,
        "candle_count": len(candles),
        "first_epoch": candles[0]["epoch"],
        "last_epoch": latest_epoch,
        "age_seconds": age_seconds,
        "fresh": age_seconds <= max(120, TIMEFRAMES[canonical_timeframe] * 2),
        "candle_source": "deriv_candles" if TIMEFRAMES[canonical_timeframe] >= 60 else "tick_stream",
    }
    cache.set(cache_key, result, ANALYSIS_CACHE_SECONDS)
    return JsonResponse(result)


@login_required
def analysis_markets(request):
    return JsonResponse({"markets": _analysis_markets()})


@login_required
def analysis_contracts(request):
    symbol = (request.GET.get("symbol") or "").strip().upper()
    if not symbol:
        return JsonResponse({"status": "error", "code": "SYMBOL_REQUIRED", "message": "A market symbol is required."}, status=400)
    try:
        market = MarketSymbol.objects.get(symbol=symbol, is_active=True, is_tradable=True)
    except MarketSymbol.DoesNotExist:
        return JsonResponse({"status": "error", "code": "MARKET_UNAVAILABLE", "message": "The selected market is not currently available from the broker catalogue."}, status=404)
    try:
        capabilities = fetch_contracts_for(market.symbol)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "BROKER_CONTRACT_DATA_FAILED",
                "message": "Deriv contract capabilities could not be confirmed.",
                "detail": str(exc),
                "symbol": market.symbol,
            },
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "broker": "Deriv",
            "symbol": market.symbol,
            "display_name": market.display_name,
            "market": market.market,
            "sub_market": market.sub_market,
            "capabilities": capabilities,
        }
    )


@login_required
def broker_account_context(request):
    """Return the selected broker account's fresh balance and risk context."""
    account = get_active_account(request.user, request=request)
    if account is None:
        return JsonResponse(
            {"status": "error", "code": "NO_ACTIVE_BROKER_ACCOUNT", "message": "No connected broker account is selected."},
            status=409,
        )
    try:
        account, broker_data = asyncio.run(
            asyncio.wait_for(
                SynchronizationService().sync_account(account),
                timeout=8.0,
            )
        )
        context = build_account_risk_context(request.user, account)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "BROKER_ACCOUNT_CONTEXT_FAILED",
                "message": "The selected broker account could not be refreshed; no synthetic balance or risk values were substituted.",
                "detail": str(exc),
            },
            status=503,
        )
    return JsonResponse({"status": "ok", "account": context, "broker_data": broker_data})


@login_required
def broker_proposal(request):
    """Return a live Deriv proposal using the selected account and risk-capped amount.

    This endpoint only prices a concrete contract; it never buys it. Every
    proposal parameter is supplied by the caller or returned by Deriv. The
    default amount comes from the selected account's risk budget.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "code": "METHOD_NOT_ALLOWED", "message": "Use POST to request a broker proposal."}, status=405)
    try:
        payload = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "code": "INVALID_JSON", "message": "A valid JSON proposal request is required."}, status=400)

    symbol = str(payload.get("symbol") or "").strip().upper()
    contract_type = str(payload.get("contract_type") or "").strip().upper()
    if not symbol or not contract_type:
        return JsonResponse({"status": "error", "code": "CONTRACT_PARAMETERS_REQUIRED", "message": "Symbol and broker contract type are required."}, status=400)

    try:
        market = MarketSymbol.objects.get(symbol=symbol, is_active=True, is_tradable=True)
    except MarketSymbol.DoesNotExist:
        return JsonResponse({"status": "error", "code": "MARKET_UNAVAILABLE", "message": "The selected market is not currently available from the broker catalogue."}, status=404)

    account = get_active_account(request.user, request=request)
    if account is None:
        return JsonResponse({"status": "error", "code": "NO_ACTIVE_BROKER_ACCOUNT", "message": "Select a connected broker account before requesting a proposal."}, status=409)

    try:
        synced_account, _broker_data = asyncio.run(
            asyncio.wait_for(
                SynchronizationService().sync_account(account),
                timeout=8.0,
            )
        )
        account = synced_account
        capabilities = fetch_contracts_for(symbol)
        allowed = {str(v).upper() for v in capabilities.get("available_contract_types", [])}
        if contract_type not in allowed:
            return JsonResponse({"status": "error", "code": "CONTRACT_NOT_AVAILABLE", "message": f"{contract_type} is not currently offered by Deriv for {symbol}.", "available_contract_types": sorted(allowed)}, status=422)

        confidence = payload.get("confidence")
        risk_context = build_account_risk_context(
            request.user,
            account,
            signal=payload.get("signal"),
            confidence=confidence,
            volatility=payload.get("volatility"),
        )
        amount = payload.get("amount")
        if amount in (None, ""):
            amount = risk_context["recommended_stake"]
        amount_decimal = Decimal(str(amount))
        recommended_decimal = Decimal(str(risk_context["recommended_stake"]))
        if amount_decimal <= 0:
            return JsonResponse({"status": "error", "code": "NO_RISK_BUDGET", "message": "The selected account has no broker-available risk budget for this proposal.", "account_context": risk_context}, status=422)
        if amount_decimal > recommended_decimal:
            return JsonResponse({"status": "error", "code": "RISK_BUDGET_EXCEEDED", "message": "Requested stake exceeds the selected account's calculated risk budget.", "requested_amount": str(amount_decimal), "recommended_stake": str(recommended_decimal), "account_context": risk_context}, status=422)

        from apps.brokers.deriv_execution import DerivTradingOperations
        proposal = asyncio.run(
            asyncio.wait_for(
                DerivTradingOperations(account).proposal(
                    symbol=symbol,
                    contract_type=contract_type,
                    amount=amount_decimal,
                    currency=account.currency,
                    duration=payload.get("duration"),
                    duration_unit=payload.get("duration_unit") or "s",
                    basis=payload.get("basis") or "stake",
                    barrier=payload.get("barrier"),
                    multiplier=payload.get("multiplier"),
                    growth_rate=payload.get("growth_rate"),
                ),
                timeout=8.0,
            )
        )
    except Exception as exc:
        return JsonResponse({"status": "error", "code": "BROKER_PROPOSAL_FAILED", "message": "Deriv did not return a usable proposal for the supplied contract parameters.", "detail": str(exc)}, status=502)

    return JsonResponse({
        "status": "ok",
        "broker": "Deriv",
        "symbol": symbol,
        "contract_type": contract_type,
        "account_context": risk_context,
        "proposal": proposal,
    })
