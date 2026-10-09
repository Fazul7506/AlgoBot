from __future__ import annotations

import asyncio
import hashlib
import json
import time
from decimal import Decimal

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.analysis.advanced import analyze_candles
from apps.analysis.broker_intelligence import build_account_risk_context
from apps.brokers.services import BrokerRegistry, SynchronizationService
from core.account_context import get_active_account
from apps.market_data.models import MarketSnapshot, MarketSymbol
from apps.strategies.models import StrategySignal
from apps.market_data.deriv_sync import fetch_contracts_for, fetch_tick
from apps.market_data.historical import fetch_and_store, fetch_and_store_ticks
from apps.market_data.constants import TIMEFRAMES
from apps.market_data.research_data import ResearchDataService
from apps.ai_engine.services import PredictionService, RecommendationService


ANALYSIS_MARKETS_CACHE_SECONDS = 15
ANALYSIS_CACHE_SECONDS = 3
STRATEGY_BASELINE_MAX_AGE_SECONDS = 300


def _latest_strategy_baseline(request, account, symbol, timeframe):
    """Read the latest persisted strategy result for the active broker account.

    This is observation-only: it never runs a strategy or triggers execution.
    """
    if account is None:
        return None
    return (
        StrategySignal.objects.select_related("strategy", "configuration")
        .filter(
            configuration__user=request.user,
            configuration__broker_account=account,
            configuration__symbol=symbol,
            configuration__timeframe=timeframe,
            configuration__is_active=True,
            configuration__enabled=True,
            strategy__enabled=True,
            timestamp__lte=timezone.now(),
        )
        .order_by("-timestamp")
        .first()
    )



def _authenticated_contract_capabilities(account, symbol):
    """Fetch broker contract capabilities through the selected account session.

    Contract availability is account/broker scoped. Never expose or persist the
    OAuth token; only broker-published capability metadata is returned.
    """
    adapter = BrokerRegistry().adapter(account.broker, account)
    available = asyncio.run(adapter.get_trade_capabilities(symbol))
    if not isinstance(available, list):
        raise RuntimeError("Deriv returned an invalid contract capability payload")
    contracts = [item for item in available if isinstance(item, dict) and item.get("contract_type")]
    return {
        "symbol": symbol,
        "source": "deriv_authenticated_contracts_for",
        "available": contracts,
        "available_contract_types": sorted({str(item.get("contract_type")) for item in contracts if item.get("contract_type")}),
        "available_contract_families": sorted({str(item.get("contract_category")) for item in contracts if item.get("contract_category")}),
        "market_types": sorted({str(item.get("market")) for item in contracts if item.get("market")}),
        "submarkets": sorted({str(item.get("submarket")) for item in contracts if item.get("submarket")}),
        "expiry_types": sorted({str(item.get("expiry_type")) for item in contracts if item.get("expiry_type")}),
        "sentiments": sorted({str(item.get("sentiment")) for item in contracts if item.get("sentiment")}),
        "barriers": sorted({str(value) for item in contracts for value in (item.get("barriers") or []) if value not in (None, "")}),
        "fetched_at": int(time.time()),
    }


def _select_validated_contract(capabilities, direction=None, timeframe=None):
    """Select one broker-published contract for research display.

    This is a broker-capability selection, not a claim of profitability or
    seasonal superiority. Only an entry returned by Deriv's contracts_for
    response can be selected. Direction and timeframe are used as observable
    research context; no seasonal assumption is invented.
    """
    if not isinstance(capabilities, dict):
        return None
    available = capabilities.get("available") or []
    if not isinstance(available, list):
        return None
    direction = str(direction or "").upper()
    if direction not in {"BUY", "SELL"}:
        return None
    preferred_sentiment = "up" if direction == "BUY" else "down"
    timeframe = str(timeframe or "").upper()

    directional_types = {
        "BUY": {"CALL", "RISE", "HIGHER", "UPORDOWN", "MULTUP", "TURBOSLONG", "VANILLALONGCALL"},
        "SELL": {"PUT", "FALL", "LOWER", "UPORDOWN", "MULTDOWN", "TURBOSSHORT", "VANILLALONGPUT"},
    }

    def score(item):
        contract_type = str(item.get("contract_type") or "").upper()
        sentiment = str(item.get("sentiment") or "").lower()
        expiry = str(item.get("expiry_type") or "").lower()
        value = 0
        if preferred_sentiment and sentiment == preferred_sentiment:
            value += 100
        if direction and contract_type in directional_types.get(direction, set()):
            value += 50
        if timeframe in {"M1", "M5", "M15", "M30", "H1", "H4"} and expiry == "intraday":
            value += 10
        if timeframe == "D1" and expiry == "daily":
            value += 10
        return value

    candidates = [
        item for item in available
        if isinstance(item, dict)
        and item.get("contract_type")
        and item.get("contract_category")
        and (not preferred_sentiment or str(item.get("sentiment") or "").lower() == preferred_sentiment or str(item.get("contract_type") or "").upper() in directional_types.get(direction, set()))
    ]
    if not candidates:
        return None
    selected = sorted(
        candidates,
        key=lambda item: (-score(item), str(item.get("contract_type") or ""), str(item.get("contract_category") or "")),
    )[0]
    return {
        "contract_type": str(selected.get("contract_type")),
        "contract_family": str(selected.get("contract_category")),
        "expiry_type": selected.get("expiry_type"),
        "sentiment": selected.get("sentiment"),
        "symbol": selected.get("underlying_symbol"),
        "source": "deriv_contracts_for",
        "selection_basis": "broker capability + signal direction + timeframe",
    }


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



@api_view(["GET"])
@permission_classes([IsAuthenticated])
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
    strategy_baseline = _latest_strategy_baseline(
        request, active_account, market.symbol, canonical_timeframe.upper()
    )
    try:
        if active_account is not None and getattr(active_account.broker, "broker_type", "") == "deriv":
            broker_capabilities = _authenticated_contract_capabilities(active_account, market.symbol)
        else:
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
    # The analysis page is also an AI inference surface, but only from the
    # same broker-ingested candles shown above. No heuristic confidence is
    # promoted to an executable signal.
    ai_result = {
        "status": "unavailable",
        "decision": None,
        "signal": None,
        "confidence": None,
        "models_used": 0,
        "model_types": [],
        "reason": "A validated trained ensemble is required before an analysis can become an executable signal.",
    }
    if len(candles) >= 25:
        try:
            prediction = PredictionService().predict(
                market.symbol,
                canonical_timeframe,
                {
                    "candles": candles,
                    "market_data": {
                        **candles[-1],
                        "price": candles[-1].get("close"),
                    },
                    "indicators": result.get("indicators", {}),
                    "smart_money": {
                        "confluence_score": result.get("technical_score", 0) / 100.0,
                        "structure": result.get("market_structure", {}),
                    },
                },
            )
            consensus = prediction.payload.get("consensus") or {}
            recommendation = RecommendationService().recommend(market.symbol, prediction)
            models_used = int(consensus.get("models_used", 0) or 0)
            raw_confidence = consensus.get("confidence")
            confidence = float(raw_confidence) * 100.0 if raw_confidence is not None else None
            raw_probability = consensus.get("probability")
            probability = float(raw_probability) if raw_probability is not None else None
            raw_agreement = consensus.get("agreement")
            agreement = float(raw_agreement) if raw_agreement is not None else None
            raw_decision = str(consensus.get("decision") or "").upper()
            decision = raw_decision if raw_decision in {"BUY", "SELL", "AVOID"} else None
            valid_ai_output = models_used > 0 and decision in {"BUY", "SELL"} and confidence is not None
            ai_result = {
                "status": "ok" if valid_ai_output and recommendation.recommendation == decision else "no_trade" if models_used > 0 else "unavailable",
                "decision": decision,
                "signal": (
                    "Strong Bullish" if valid_ai_output and recommendation.recommendation == "BUY" and decision == "BUY" and confidence >= 80
                    else "Bullish" if valid_ai_output and recommendation.recommendation == "BUY" and decision == "BUY"
                    else "Strong Bearish" if valid_ai_output and recommendation.recommendation == "SELL" and decision == "SELL" and confidence >= 80
                    else "Bearish" if valid_ai_output and recommendation.recommendation == "SELL" and decision == "SELL"
                    else None
                ),
                "confidence": round(confidence, 2) if confidence is not None else None,
                "models_used": models_used,
                "model_types": consensus.get("model_types", []),
                "probability": probability,
                "agreement": agreement,
                "recommendation": recommendation.recommendation if models_used > 0 else None,
                "recommendation_confidence": float(recommendation.confidence) if models_used > 0 else None,
                "prediction_id": prediction.id,
                "reason": recommendation.reason if models_used > 0 else "No validated trained model is currently available.",
                "source": prediction.payload.get("source"),
            }
        except Exception as exc:
            log.warning(
                "Analysis AI inference unavailable",
                extra={"symbol": market.symbol, "timeframe": canonical_timeframe, "error": str(exc)[:200]},
            )
            ai_result = {
                "status": "unavailable",
                "decision": None,
                "signal": None,
                "confidence": None,
                "models_used": 0,
                "model_types": [],
                "probability": None,
                "agreement": None,
                "recommendation": None,
                "recommendation_confidence": None,
                "prediction_id": None,
                "reason": "AI analysis is currently unavailable; no AI signal or confidence was substituted.",
                "source": None,
            }
    result["ai"] = ai_result
    result["signal"] = ai_result["signal"]
    result["confidence"] = ai_result["confidence"]
    result["score"] = result.get("technical_score")
    strategy_direction = str(strategy_baseline.signal or "").upper() if strategy_baseline else None
    strategy_age = (
        max(0, int((timezone.now() - strategy_baseline.timestamp).total_seconds()))
        if strategy_baseline else None
    )
    strategy_fresh = strategy_age is not None and strategy_age <= STRATEGY_BASELINE_MAX_AGE_SECONDS
    strategy_ready = strategy_fresh and strategy_direction in {"BUY", "SELL"}
    ai_direction = ai_result.get("decision")
    strategy_confluence = strategy_ready and ai_direction in {"BUY", "SELL"} and strategy_direction == ai_direction
    result["execution_gate"] = {
        "data_fresh": False,
        "sufficient_history": len(candles) >= 251,
        "strategy_ready": strategy_ready,
        "strategy_confluence": strategy_confluence,
        "ai_ready": ai_result["models_used"] > 0 and ai_result["decision"] in {"BUY", "SELL"} and ai_result.get("confidence") is not None and ai_result.get("recommendation") == ai_result["decision"],
        "broker_contracts_confirmed": bool(broker_capabilities.get("available_contract_types")),
        "account_scope_confirmed": bool(active_account is not None and getattr(active_account, "user_id", request.user.pk) == request.user.pk),
        "account_ready": False,
        "risk_ready": False,
        "live_quote_confirmed": False,
        "live_quote_fresh": False,
        "ready": False,
        "reason": "Final execution readiness requires fresh market data, a ready selected account, risk capacity, broker capabilities and a fresh live quote.",
    }
    account_context = None
    broker_data = None
    if active_account is not None:
        try:
            if refresh_requested:
                synced_account, broker_data = asyncio.run(
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
                broker_data=broker_data,
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
    result["execution_gate"]["data_fresh"] = bool(
        result["data_provenance"]["age_seconds"] <= max(120, TIMEFRAMES[canonical_timeframe] * 2)
    )
    live_quote_age = None
    if refresh_requested and live_tick and live_tick.get("quote") is not None and live_tick.get("epoch") is not None:
        live_quote_age = max(0, int(time.time()) - int(live_tick["epoch"]))
    result["live_quote"] = {
        "price": float(live_tick["quote"]) if refresh_requested and live_tick and live_tick.get("quote") is not None else None,
        "epoch": int(live_tick["epoch"]) if refresh_requested and live_tick and live_tick.get("epoch") is not None else None,
        "age_seconds": live_quote_age,
        "fresh": live_quote_age is not None and live_quote_age <= 5,
        "source": "deriv_public_websocket" if live_tick else None,
    }
    result["execution_gate"]["live_quote_confirmed"] = bool(
        refresh_requested and live_tick and live_tick.get("quote") is not None
    )
    result["execution_gate"]["live_quote_fresh"] = bool(result["live_quote"]["fresh"])
    result["execution_gate"]["account_ready"] = bool(
        active_account is not None
        and getattr(active_account, "token_status", "") == "active"
        and not getattr(active_account, "is_token_expired", False)
    )
    recommended_stake = account_context.get("recommended_stake") if account_context else None
    try:
        result["execution_gate"]["risk_ready"] = recommended_stake is not None and float(recommended_stake) > 0
    except (TypeError, ValueError):
        result["execution_gate"]["risk_ready"] = False
    result["execution_gate"]["ready"] = all(
        (
            result["execution_gate"]["data_fresh"],
            result["execution_gate"]["sufficient_history"],
            result["execution_gate"]["ai_ready"],
            result["execution_gate"]["broker_contracts_confirmed"],
            result["execution_gate"]["account_scope_confirmed"],
            result["execution_gate"]["account_ready"],
            result["execution_gate"]["risk_ready"],
            result["execution_gate"]["live_quote_confirmed"],
            result["execution_gate"]["live_quote_fresh"],
            result["execution_gate"]["strategy_ready"],
            result["execution_gate"]["strategy_confluence"],
        )
    )
    if not result["execution_gate"]["ready"]:
        result["trade_spec"]["direction"] = None
        result["trade_spec"]["entry_condition"] = "NO TRADE until every execution gate is confirmed"

    gate = result["execution_gate"]
    technical_score = result.get("technical_score")
    ai_ready = bool(gate["ai_ready"])
    broker_ready = bool(gate["broker_contracts_confirmed"])
    account_ready = bool(gate["account_scope_confirmed"] and gate["account_ready"])
    live_ready = bool(gate["live_quote_confirmed"] and gate["live_quote_fresh"])
    risk_ready = bool(gate["risk_ready"])
    result["research_state"] = "READY" if gate["data_fresh"] else "STALE"
    result["broker_state"] = "BROKER_CONNECTED" if live_ready and broker_ready else "BROKER_UNAVAILABLE" if not gate["live_quote_confirmed"] else "BROKER_CONNECTED"
    result["analysis_layers"] = {
        "market_data": {
            "state": "READY" if gate["data_fresh"] else "STALE",
            "source": "Deriv market data",
            "candle_count": len(candles),
            "fresh": bool(gate["data_fresh"]),
        },
        "technical": {
            "state": "READY" if technical_score is not None else "UNAVAILABLE",
            "score": technical_score,
            "indicators": result.get("indicators", {}),
            "structure": result.get("structure"),
            "volatility_regime": result.get("volatility_regime"),
            "factors": result.get("factors") or [],
        },
        "strategy": {
            "state": "READY" if strategy_ready else "STALE" if strategy_baseline else "UNAVAILABLE",
            "direction": strategy_direction if strategy_ready else None,
            "confidence": float(strategy_baseline.confidence) if strategy_baseline and strategy_baseline.confidence is not None else None,
            "timestamp": strategy_baseline.timestamp.isoformat() if strategy_baseline else None,
            "age_seconds": strategy_age,
            "strategy": strategy_baseline.strategy.name if strategy_baseline else None,
            "version": strategy_baseline.strategy.version if strategy_baseline else None,
            "evidence": (strategy_baseline.metadata or {}).get("criteria", {}) if strategy_baseline else [],
        },
        "ai": {
            "state": "READY" if ai_ready else result["ai"].get("status", "not_ready"),
            "decision": result["ai"].get("decision"),
            "confidence": result["ai"].get("confidence"),
            "models_used": result["ai"].get("models_used", 0),
            "agreement": result["ai"].get("agreement"),
            "source": result["ai"].get("source"),
        },
    }
    evidence = []
    for key, passed, label in (
        ("market_data", gate["data_fresh"], "fresh market data"),
        ("technical", technical_score is not None, "technical evidence"),
        ("strategy", strategy_ready, "fresh strategy result"),
        ("strategy_confluence", strategy_confluence, "strategy and AI direction agree"),
        ("ai", ai_ready, "validated AI decision"),
        ("broker", broker_ready, "broker contract capability"),
        ("account", account_ready, "selected account"),
        ("risk", risk_ready, "risk capacity"),
        ("live_quote", live_ready, "fresh live quote"),
    ):
        evidence.append({"layer": key, "condition": label, "passed": bool(passed)})
    result["confluence"] = {
        "state": "CONFIRMED" if all(item["passed"] for item in evidence) else "CONDITIONAL",
        "direction": result.get("trade_spec", {}).get("direction") if gate["ready"] else None,
        "evidence": evidence,
        "score": None,
        "note": "Confluence is evidence alignment; it is not an execution fact.",
    }
    result["signal_validation"] = {
        "state": "ACTIONABLE" if gate["ready"] else "WAITING_FOR_CONFIRMATION",
        "signal": result.get("signal") if gate["ready"] else None,
        "generated_at": result.get("data_provenance", {}).get("last_epoch"),
        "expires_after_seconds": max(120, TIMEFRAMES[canonical_timeframe] * 2),
        "no_look_ahead": True,
        "execution_separate": True,
    }
    cache.set(cache_key, result, ANALYSIS_CACHE_SECONDS)
    return JsonResponse(result)


def _analysis_markets():
    cached = cache.get("algobot:analysis:markets:v1")
    if cached is not None:
        return cached
    markets = list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .values("symbol", "display_name", "market", "sub_market")
        .order_by("market", "symbol")
    )
    cache.set("algobot:analysis:markets:v1", markets, ANALYSIS_MARKETS_CACHE_SECONDS)
    return markets


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_markets(request):
    return JsonResponse({"markets": _analysis_markets()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_contracts(request):
    symbol = (request.GET.get("symbol") or "").strip().upper()
    if not symbol:
        return JsonResponse({"status": "error", "code": "SYMBOL_REQUIRED", "message": "A market symbol is required."}, status=400)
    try:
        market = MarketSymbol.objects.get(symbol=symbol, is_active=True, is_tradable=True)
    except MarketSymbol.DoesNotExist:
        return JsonResponse({"status": "error", "code": "MARKET_UNAVAILABLE", "message": "The selected market is not currently available from the broker catalogue."}, status=404)
    account = get_active_account(request.user, request=request)
    if account is None:
        return JsonResponse({"status": "error", "code": "NO_ACTIVE_BROKER_ACCOUNT", "message": "Select a connected Deriv broker account before loading contract capabilities."}, status=409)
    if account.broker.broker_type != "deriv":
        return JsonResponse({"status": "error", "code": "BROKER_NOT_SUPPORTED", "message": "Contract capability synchronization currently requires the selected Deriv account."}, status=422)
    try:
        account, _broker_data = asyncio.run(asyncio.wait_for(SynchronizationService().sync_account(account), timeout=8.0))
        capabilities = _authenticated_contract_capabilities(account, market.symbol)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "BROKER_CONTRACT_DATA_FAILED",
                "message": "Deriv contract capabilities could not be confirmed from the selected broker account.",
                "detail": str(exc),
                "symbol": market.symbol,
            },
            status=503,
        )
    direction = str(request.GET.get("direction") or "").upper()
    timeframe = str(request.GET.get("timeframe") or "").upper()
    selected_contract = _select_validated_contract(capabilities, direction=direction, timeframe=timeframe)
    return JsonResponse(
        {
            "status": "ok",
            "broker": "Deriv",
            "symbol": market.symbol,
            "display_name": market.display_name,
            "market": market.market,
            "sub_market": market.sub_market,
            "capabilities": capabilities,
            "selected_contract": selected_contract,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
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
        context = build_account_risk_context(request.user, account, broker_data=broker_data)
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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
