import asyncio
import json
import logging
import math
import time
from datetime import datetime
from decimal import InvalidOperation

import websockets
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from apps.brokers.exceptions import BrokerConnectionError
from apps.analysis.broker_intelligence import build_account_risk_context
from apps.strategies.models import StrategySignal
from core.account_context import get_active_account

from .models import MarketSnapshot, MarketSymbol
from .deriv_sync import sync_active_symbols

LIVE_TICK_MAX_AGE_SECONDS = 5
ANALYSIS_BASELINE_MAX_AGE_SECONDS = 900
DEFAULT_CONFIDENCE_THRESHOLD = 70.0
MAX_SCAN_SYMBOLS = 80
LIVE_TICK_SCAN_TIMEOUT_SECONDS = 12.0
LIVE_SNAPSHOT_MAX_AGE_SECONDS = 5

log = logging.getLogger(__name__)


def _selected_deriv_account(request):
    """Use the canonical server-side active account context."""
    return get_active_account(request.user, request=request, broker_type="deriv")


def _as_float(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, InvalidOperation, OverflowError):
        return None


def _normalize_live_tick(tick):
    """Reject malformed or future quotes before they count as live market data."""
    if not isinstance(tick, dict):
        return None
    quote = _as_float(tick.get("quote"))
    epoch = _as_float(tick.get("epoch"))
    if quote is None or epoch is None or epoch <= 0 or epoch > time.time() + 5:
        return None
    return {**tick, "quote": quote, "epoch": int(epoch)}


def _meta_first(metadata, *keys):
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _analysis_timeframe(signal):
    if signal.configuration and signal.configuration.timeframe:
        return str(signal.configuration.timeframe)
    return None


def _analysis_baselines(request, symbols, timeframe, account=None):
    """Return only signals bound to the authenticated active broker account."""
    if account is None:
        return {}
    qs = (StrategySignal.objects.select_related("strategy", "configuration")
          .filter(
              configuration__user=request.user,
              configuration__broker_account=account,
              configuration__is_active=True,
              configuration__enabled=True,
              strategy__enabled=True,
              symbol__in=symbols,
              timestamp__lte=timezone.now(),
          )
          .order_by("-timestamp"))
    baselines = {}
    for signal in qs:
        if timeframe and _analysis_timeframe(signal) != timeframe:
            continue
        if signal.symbol not in baselines:
            baselines[signal.symbol] = signal
    return baselines


def _trade_context(signal, market, account, timeframe=None):
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    configuration = signal.configuration
    criteria = configuration.criteria if configuration and isinstance(configuration.criteria, dict) else {}
    parameters = configuration.parameters if configuration and isinstance(configuration.parameters, dict) else {}
    merged = {**parameters, **criteria, **metadata}
    return {
        "market_type": _meta_first(merged, "market_type", "market", "asset_class") or getattr(market, "market", None),
        "sub_market": _meta_first(merged, "sub_market", "submarket", "market_subtype") or getattr(market, "sub_market", None),
        "symbol": signal.symbol,
        "instrument": getattr(market, "display_name", None) or _meta_first(merged, "display_name", "instrument_name") or signal.symbol,
        "trade_type": _meta_first(merged, "trade_type", "trade_side", "order_type") or signal.signal,
        "direction": signal.signal,
        "contract_type": _meta_first(merged, "contract_type", "contract", "contract_code"),
        "contract_family": _meta_first(merged, "contract_family", "contract_category", "contract_group"),
        "duration": _meta_first(merged, "duration", "expiry_duration", "period"),
        "duration_unit": _meta_first(merged, "duration_unit", "duration_type", "period_unit"),
        "barrier": _meta_first(merged, "barrier", "barrier_value", "strike"),
        "stake": _meta_first(merged, "stake", "amount", "risk_amount"),
        "payout": _meta_first(merged, "payout", "potential_payout", "profit_potential"),
        "currency": account.currency,
        "account_type": account.account_type,
        "broker": account.broker.name,
        "timeframe": timeframe or _analysis_timeframe(signal),
        "strategy": signal.strategy.name,
        "strategy_version": signal.strategy.version,
        "strategy_category": signal.strategy.category,
        "risk_profile": configuration.risk_profile if configuration else _meta_first(merged, "risk_profile", "risk_mode"),
        "schedule": configuration.schedule if configuration else _meta_first(merged, "schedule", "signal_schedule"),
        "entry_condition": _meta_first(merged, "entry_condition", "trigger_condition", "entry_trigger"),
        "trigger_status": _meta_first(merged, "trigger_status", "trigger", "status"),
        "confirmation": _meta_first(merged, "confirmation", "confirmation_sequence", "confirmation_status"),
        "market_regime": _meta_first(merged, "market_regime", "regime", "volatility_regime"),
        "execution_mode": _meta_first(merged, "execution_mode", "execution", "mode"),
        "quote_type": _meta_first(merged, "quote_type", "price_source"),
        "entry_price": str(signal.entry_price) if signal.entry_price is not None else None,
        "stop_loss": str(signal.stop_loss) if signal.stop_loss is not None else None,
        "take_profit": str(signal.take_profit) if signal.take_profit is not None else None,
    }


async def _live_deriv_ticks(symbols):
    """Read current Deriv quotes from the broker's public market-data channel.

    Deriv documents the public Options WebSocket as the authoritative no-auth
    channel for real-time ticks. Account OTP authentication is reserved for
    account-scoped operations such as trading and balances. Keeping quote
    retrieval on the public market-data channel prevents an OAuth trade-scope
    or account OTP problem from incorrectly making every market appear to
    have no live price.
    """
    unique_symbols = list(dict.fromkeys(str(symbol).strip() for symbol in symbols if str(symbol).strip()))
    if not unique_symbols:
        return {}, 0

    endpoint = getattr(settings, "DERIV_PUBLIC_WS_URL", "").strip()
    if not endpoint:
        raise BrokerConnectionError("DERIV_PUBLIC_WS_URL is not configured")

    started = time.monotonic()
    results = {}
    req_to_symbol = {index: symbol for index, symbol in enumerate(unique_symbols, start=1)}
    deadline = started + LIVE_TICK_SCAN_TIMEOUT_SECONDS

    try:
        async with websockets.connect(
            endpoint,
            open_timeout=5,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=10,
            max_size=2**20,
        ) as ws:
            for req_id, symbol in req_to_symbol.items():
                await ws.send(json.dumps({"ticks": symbol, "subscribe": 1, "req_id": req_id}))

            while len(results) < len(req_to_symbol):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(1.5, remaining))
                except asyncio.TimeoutError:
                    break

                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    continue

                if payload.get("error"):
                    error = payload.get("error") or {}
                    log.warning(
                        "Deriv public tick request failed",
                        extra={
                            "symbol": req_to_symbol.get(payload.get("req_id")),
                            "code": str(error.get("code") or "")[:80],
                            "error_message": str(error.get("message") or "")[:200],
                        },
                    )
                    continue
                if payload.get("msg_type") != "tick":
                    continue

                tick = payload.get("tick") or {}
                symbol = str(tick.get("symbol") or req_to_symbol.get(payload.get("req_id"), ""))
                if symbol not in req_to_symbol.values():
                    continue

                quote = _as_float(tick.get("quote"))
                epoch = _as_float(tick.get("epoch"))
                if quote is None or epoch is None or epoch <= 0 or epoch > time.time() + 5:
                    continue

                results[symbol] = tick
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
        raise BrokerConnectionError("Deriv public live market data is temporarily unavailable") from exc

    return results, round((time.monotonic() - started) * 1000, 1)

def _persisted_live_ticks(markets):
    """Read the latest broker ticks persisted by the continuous Deriv stream."""
    now = timezone.now()
    results = {}
    snapshots = MarketSnapshot.objects.filter(symbol__in=markets).select_related("symbol")
    for snapshot in snapshots:
        age = (now - snapshot.timestamp).total_seconds()
        if age < -5 or age > LIVE_SNAPSHOT_MAX_AGE_SECONDS:
            continue
        quote = _as_float(snapshot.last_price)
        if quote is None:
            continue
        results[snapshot.symbol.symbol] = {
            "symbol": snapshot.symbol.symbol,
            "quote": quote,
            "bid": _as_float(snapshot.bid),
            "ask": _as_float(snapshot.ask),
            "epoch": int(snapshot.timestamp.timestamp()),
            "_source": "deriv_public_stream",
        }
    return results




def _signal_evidence(signal):
    """Expose only evidence that was actually persisted by the strategy run."""
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    evidence = []
    criteria = metadata.get("criteria")
    if isinstance(criteria, dict):
        for key, value in criteria.items():
            if key in {"passed", "reasons"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                outcome = ("PASS" if value else "FAIL") if isinstance(value, bool) else "OBSERVED"
                evidence.append({"condition": str(key), "observed": value, "result": outcome})
    indicators = metadata.get("indicators") or metadata.get("indicator_data")
    if isinstance(indicators, dict):
        for key, value in indicators.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                evidence.append({"condition": str(key), "observed": value, "result": "OBSERVED"})
    for key in ("market_regime", "trend", "momentum", "confirmation"):
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)):
            evidence.append({"condition": key, "observed": value, "result": "OBSERVED"})
    return evidence[:30]

def _signal_lifecycle(*, baseline, live_tick, status, direction, execution_ready):
    """Map observed validation state to the canonical Signals lifecycle."""
    if baseline is None:
        return "ANALYSING"
    if status == "ANALYSIS_STALE":
        return "STALE"
    if status == "SIGNAL_EXPIRED":
        return "EXPIRED"
    if status in {"LIVE_DATA_STALE"}:
        return "STALE"
    if status in {"LIVE_CONFIRMATION_UNAVAILABLE", "LIVE_DATA_UNAVAILABLE"}:
        return "WAITING_FOR_CONFIRMATION"
    if status == "LIVE_CONFIRMATION_FAILED":
        return "INVALIDATED"
    if status == "LIVE_CONFIDENCE_BELOW_GATE":
        return "BLOCKED"
    if status == "ACCOUNT_AUTH_REQUIRED":
        return "BLOCKED"
    if execution_ready:
        return "ACTIONABLE"
    if direction in {"BUY", "SELL"}:
        return "CANDIDATE"
    return "WAITING_FOR_CONFIRMATION"


def _revise_signal(signal, live_tick, now, market, account):
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    baseline_direction = str(signal.signal or "").upper()
    raw_confidence = _as_float(signal.confidence)
    base_confidence = max(0.0, min(100.0, raw_confidence)) if raw_confidence is not None else None
    analysis_age = max(0, int((now - signal.timestamp).total_seconds()))
    live_epoch = int(live_tick.get("epoch"))
    live_age = max(0, int(time.time()) - live_epoch)
    live_price = _as_float(live_tick.get("quote"))
    entry = _as_float(signal.entry_price)
    revised = base_confidence
    confidence_source = "strategy_signal" if base_confidence is not None else None
    evidence = ["analysis_baseline_loaded", "deriv_public_live_tick"]
    status = "LIVE_REVIEW"
    direction = baseline_direction
    expiry_value = _meta_first(metadata, "expires_at", "expiry_at", "valid_until", "expires")
    expired = False
    if expiry_value not in (None, ""):
        try:
            if isinstance(expiry_value, (int, float)):
                expired = float(expiry_value) <= time.time()
            else:
                expiry = datetime.fromisoformat(str(expiry_value).replace("Z", "+00:00"))
                if timezone.is_naive(expiry):
                    expiry = timezone.make_aware(expiry, timezone.get_current_timezone())
                expired = expiry <= now
        except (TypeError, ValueError, OverflowError):
            expired = False
    if expired:
        status = "SIGNAL_EXPIRED"
        direction = None
        evidence.append("signal_expiry_reached")
    elif analysis_age > ANALYSIS_BASELINE_MAX_AGE_SECONDS:
        status = "ANALYSIS_STALE"
        direction = None
        evidence.append("analysis_baseline_stale")
    elif live_age > LIVE_TICK_MAX_AGE_SECONDS:
        status = "LIVE_DATA_STALE"
        direction = None
        evidence.append("live_tick_stale")
    elif baseline_direction in {"BUY", "SELL"} and live_price is not None and entry is not None:
        favorable = (baseline_direction == "BUY" and live_price >= entry) or (baseline_direction == "SELL" and live_price <= entry)
        if favorable:
            evidence.append("live_price_confirms_analysis_entry_side")
        else:
            direction = None
            status = "LIVE_CONFIRMATION_FAILED"
            evidence.append("live_price_conflicts_with_analysis_entry_side")
    elif baseline_direction in {"BUY", "SELL"}:
        status = "LIVE_CONFIRMATION_UNAVAILABLE"
        direction = None
        evidence.append("analysis_entry_price_unavailable")
    configured_threshold = _as_float(getattr(settings, "SIGNAL_LIVE_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
    threshold = max(DEFAULT_CONFIDENCE_THRESHOLD, configured_threshold if configured_threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD)
    confidence_gate = revised is not None and revised >= threshold
    signal_valid = direction in {"BUY", "SELL"} and status == "LIVE_REVIEW"
    execution_ready = signal_valid and confidence_gate
    if signal_valid and not confidence_gate:
        status = "LIVE_CONFIDENCE_BELOW_GATE"
    lifecycle = _signal_lifecycle(
        baseline=signal,
        live_tick=live_tick,
        status=status,
        direction=direction,
        execution_ready=execution_ready,
    )
    return {
        "analysis_signal_id": signal.id,
        "analysis_timestamp": signal.timestamp.isoformat(),
        "analysis_age_seconds": analysis_age,
        "baseline_direction": baseline_direction or None,
        "baseline_confidence": round(base_confidence, 2) if base_confidence is not None else None,
        "direction": direction,
        "confidence": round(revised, 2) if revised is not None else None,
        "confidence_source": confidence_source,
        "live_confidence_threshold": round(threshold, 2),
        "execution_ready": execution_ready,
        "signal_valid": signal_valid,
        "status": status,
        "lifecycle": lifecycle,
        "evidence": evidence,
        "why": _signal_evidence(signal),
        "entry_price": str(signal.entry_price) if signal.entry_price is not None else None,
        "stop_loss": str(signal.stop_loss) if signal.stop_loss is not None else None,
        "take_profit": str(signal.take_profit) if signal.take_profit is not None else None,
        "strategy": signal.strategy.name,
        "strategy_version": signal.strategy.version,
        "strategy_category": signal.strategy.category,
        "timeframe": _analysis_timeframe(signal),
        "analysis_metadata": metadata,
        "trade_context": _trade_context(signal, market, account),
        "provenance": {
            "market_data": "Deriv public market-data WebSocket",
            "analysis": "AlgoBot persisted StrategySignal",
            "strategy": f"{signal.strategy.name} v{signal.strategy.version}",
            "execution": "Not executed",
        },
        "live": {
            "price": live_price,
            "bid": _as_float(live_tick.get("bid")),
            "ask": _as_float(live_tick.get("ask")),
            "epoch": live_epoch,
            "age_seconds": live_age,
            "source": live_tick.get("_source", "deriv_public_websocket"),
        },
    }


def _strategy_signals_impl(request):
    """Return broker-sourced signal data without HTML login redirects."""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required to read live signals."}, status=401)
    account = _selected_deriv_account(request)
    if account is None:
        return JsonResponse({"status": "error", "code": "DERIV_ACCOUNT_REQUIRED", "message": "Connect and select a Deriv account before reading live signals."}, status=409)
    account_credentials_valid = bool(account.is_connection_eligible)
    account_risk_context = build_account_risk_context(request.user, account)
    symbol_filter = str(request.GET.get("symbol") or "").strip()
    timeframe = str(request.GET.get("timeframe") or "M1").strip()
    try:
        limit = min(max(int(request.GET.get("limit", 40)), 1), MAX_SCAN_SYMBOLS)
    except (TypeError, ValueError):
        limit = 40
    symbols_qs = MarketSymbol.objects.filter(is_active=True, is_tradable=True, broker="deriv").order_by("market", "symbol")
    if symbol_filter: symbols_qs = symbols_qs.filter(symbol=symbol_filter)
    markets = list(symbols_qs[:limit])
    if not markets:
        return JsonResponse({"status": "ok", "source": "deriv_public_live", "count": 0, "live_data_available_count": 0, "actionable_count": 0, "data": []})
    symbols = [market.symbol for market in markets]
    live_started = time.monotonic()
    live_ticks = _persisted_live_ticks(markets)
    missing_symbols = [symbol for symbol in symbols if symbol not in live_ticks]
    if missing_symbols:
        try:
            fallback_ticks, _fallback_latency = asyncio.run(_live_deriv_ticks(missing_symbols))
            for symbol, tick in fallback_ticks.items():
                normalized_tick = _normalize_live_tick(tick)
                if normalized_tick is None:
                    continue
                normalized_tick["_source"] = "deriv_public_websocket"
                live_ticks[symbol] = normalized_tick
        except BrokerConnectionError as exc:
            # A missing live quote remains missing. No stale or fabricated value
            # is substituted into a trading signal. Preserve the failure reason
            # in server logs without exposing broker internals to the browser.
            log.warning("Signals live Deriv feed unavailable", extra={"error": str(exc)[:200]})
            pass
    feed_latency_ms = round((time.monotonic() - live_started) * 1000, 1)
    baselines = _analysis_baselines(request, symbols, timeframe, account=account)
    now = timezone.now(); rows = []
    for market in markets:
        live_tick = live_ticks.get(market.symbol); baseline = baselines.get(market.symbol)
        row = {"symbol": market.symbol, "instrument": market.display_name, "display_name": market.display_name, "market": market.market, "sub_market": market.sub_market, "broker": "deriv", "account_id": account.account_id, "account_type": account.account_type, "timeframe": timeframe, "source": "deriv_public_stream"}
        base_context = {"market_type": market.market, "sub_market": market.sub_market, "symbol": market.symbol, "instrument": market.display_name, "trade_type": None, "direction": None, "contract_type": None, "contract_family": None, "duration": None, "duration_unit": None, "barrier": None, "stake": account_risk_context.get("recommended_stake"), "risk_budget": account_risk_context.get("risk_budget"), "payout": None, "currency": account.currency, "account_type": account.account_type, "broker": account.broker.name, "timeframe": timeframe}
        if not live_tick:
            row.update({
                "direction": None, "confidence": None, "status": "LIVE_DATA_UNAVAILABLE",
                "lifecycle": "WAITING_FOR_CONFIRMATION", "execution_ready": False,
                "signal_valid": False, "evidence": ["broker_tick_not_received"], "why": [],
                "provenance": {"market_data": "Deriv public market-data WebSocket", "analysis": "Unavailable", "execution": "Not executed"},
                "trade_context": base_context,
            })
        elif not baseline:
            live_age = max(0, int(time.time()) - int(live_tick.get("epoch")))
            row.update({
                "direction": None, "confidence": None, "status": "WAITING_FOR_ANALYSIS",
                "lifecycle": "ANALYSING", "execution_ready": False, "signal_valid": False,
                "evidence": ["live_tick_received", "no_matching_analysis_baseline"], "why": [],
                "live": {"price": _as_float(live_tick.get("quote")), "bid": _as_float(live_tick.get("bid")), "ask": _as_float(live_tick.get("ask")), "epoch": int(live_tick.get("epoch")), "age_seconds": live_age, "source": live_tick.get("_source", "deriv_public_websocket")},
                "provenance": {"market_data": "Deriv public market-data WebSocket", "analysis": "No matching StrategySignal", "execution": "Not executed"},
                "trade_context": base_context,
            })
        else:
            row.update(_revise_signal(baseline, live_tick, now, market, account))
        rows.append(row)

    risk_ready = bool(account_risk_context.get("risk_inputs_complete")) and (_as_float(account_risk_context.get("recommended_stake")) or 0) > 0
    live_mode_ready = (
        account.account_type != "real"
        or (
            bool(getattr(account.broker, "supports_live", False))
            and bool(getattr(settings, "ALLOW_LIVE_TRADING", False))
        )
    )
    for row in rows:
        if row.get("direction") not in {"BUY", "SELL"}:
            continue
        reason = None
        if not account_credentials_valid:
            reason = "selected_account_connection_not_eligible"
            row["status"] = "ACCOUNT_AUTH_REQUIRED"
        elif not risk_ready:
            reason = "risk_context_incomplete_or_zero_stake"
            row["status"] = "RISK_CONTEXT_INCOMPLETE"
        elif not live_mode_ready:
            reason = "live_account_or_platform_gate_not_enabled"
            row["status"] = "LIVE_TRADING_DISABLED"
        if reason:
            row["execution_ready"] = False
            row["signal_valid"] = False
            row["evidence"] = [*row.get("evidence", []), reason, *account_risk_context.get("risk_data_issues", [])]
            row["lifecycle"] = "BLOCKED"

    actionable = [r for r in rows if r.get("execution_ready")]
    live_data_available_count = sum(1 for r in rows if r.get("live"))
    stale_count = sum(1 for r in rows if r.get("status") in {"LIVE_DATA_STALE", "ANALYSIS_STALE"})
    broker_feed_state = (
        "BROKER_CONNECTED"
        if live_data_available_count == len(rows) and rows
        else "BROKER_PARTIAL"
        if live_data_available_count
        else "BROKER_UNAVAILABLE"
    )
    state = "ACTIONABLE" if actionable else "STALE" if stale_count else "READY" if live_data_available_count else "UNAVAILABLE"
    if not live_data_available_count:
        return JsonResponse({
            "status": "error",
            "state": "UNAVAILABLE",
            "code": "MARKET_DATA_UNAVAILABLE",
            "message": "Current Deriv market data is unavailable; no current signal state is asserted.",
            "generated_at": now.isoformat(),
            "broker_feed_state": broker_feed_state,
            "count": len(rows),
            "live_data_available_count": 0,
            "actionable_count": 0,
            "data": rows,
        }, status=503)
    return JsonResponse({
        "status": "ok", "state": state, "source": "deriv_public_live", "generated_at": now.isoformat(),
        "feed_latency_ms": feed_latency_ms,
        "research_state": "READY" if live_data_available_count else "UNAVAILABLE",
        "broker_state": broker_feed_state,
        "account": {"id": account.account_id, "type": account.account_type, "currency": account.currency, "balance": account_risk_context.get("balance"), "available_funds": account_risk_context.get("available_funds"), "recommended_stake": account_risk_context.get("recommended_stake"), "risk_budget": account_risk_context.get("risk_budget")},
        "account_risk_context": account_risk_context,
        "analysis_role": "upstream_baseline_only", "historical_candles_primary": False,
        "account_trading_enabled": account_credentials_valid,
        "live_tick_max_age_seconds": LIVE_TICK_MAX_AGE_SECONDS,
        "analysis_baseline_max_age_seconds": ANALYSIS_BASELINE_MAX_AGE_SECONDS,
        "signal_lifecycle": ["ANALYSING", "CANDIDATE", "WAITING_FOR_CONFIRMATION", "ACTIONABLE", "STALE", "EXPIRED", "INVALIDATED", "BLOCKED", "EXECUTED"],
        "broker_feed_state": broker_feed_state,
        "count": len(rows), "live_data_available_count": live_data_available_count, "stale_count": stale_count,
        "actionable_count": len(actionable), "data": rows,
    })


def strategy_signals(request):
    """Return the canonical Signals JSON contract without leaking HTML errors."""
    try:
        return _strategy_signals_impl(request)
    except Exception:
        log.exception(
            "Signals API failed",
            extra={
                "user_id": getattr(request.user, "pk", None),
                "symbol": str(request.GET.get("symbol") or "")[:40],
                "timeframe": str(request.GET.get("timeframe") or "M1")[:16],
            },
        )
        return JsonResponse(
            {
                "status": "error",
                "code": "SIGNAL_SERVICE_ERROR",
                "message": "Signal service temporarily unavailable.",
            },
            status=500,
        )
