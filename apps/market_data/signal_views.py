import asyncio
import json
import time
from decimal import InvalidOperation

import websockets
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from apps.brokers.exceptions import BrokerConnectionError
from apps.brokers.models import BrokerAccount
from apps.strategies.models import StrategySignal

from .models import MarketSymbol

LIVE_TICK_MAX_AGE_SECONDS = 5
ANALYSIS_BASELINE_MAX_AGE_SECONDS = 900
DEFAULT_CONFIDENCE_THRESHOLD = 70.0
MAX_SCAN_SYMBOLS = 80
LIVE_TICK_SCAN_TIMEOUT_SECONDS = 8.0


def _selected_deriv_account(request):
    qs = BrokerAccount.objects.filter(user=request.user, status="active", broker__status="active", broker__broker_type="deriv").select_related("broker")
    selected_id = request.session.get("active_broker_account_id")
    if selected_id:
        account = qs.filter(pk=selected_id).first()
        if account:
            return account
    return qs.order_by("-last_synced_at", "-id").first()


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _meta_first(metadata, *keys):
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _analysis_timeframe(signal):
    if signal.configuration and signal.configuration.timeframe:
        return str(signal.configuration.timeframe)
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    return str(metadata.get("timeframe") or metadata.get("interval") or "M1")


def _analysis_baselines(request, symbols, timeframe, account=None):
    qs = StrategySignal.objects.select_related("strategy", "configuration").filter(Q(configuration__user=request.user) | Q(configuration__isnull=True), symbol__in=symbols).order_by("-timestamp")
    baselines = {}
    selected = request.session.get("active_broker_account_id")
    selected_id = int(selected) if str(selected).isdigit() else None
    account_id = getattr(account, "pk", None)
    for signal in qs:
        if timeframe and _analysis_timeframe(signal) != timeframe:
            continue
        signal_account_id = signal.configuration.broker_account_id if signal.configuration else None
        if signal_account_id:
            expected_id = selected_id or account_id
            if expected_id is None or signal_account_id != expected_id:
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
        "quote_type": _meta_first(merged, "quote_type", "price_source") or "deriv_public_websocket",
        "entry_price": str(signal.entry_price) if signal.entry_price is not None else None,
        "stop_loss": str(signal.stop_loss) if signal.stop_loss is not None else None,
        "take_profit": str(signal.take_profit) if signal.take_profit is not None else None,
    }


async def _live_deriv_ticks(symbols):
    """Read current Deriv quotes from one public broker market-data stream.

    The public Options WebSocket is the authoritative no-auth source for live
    quotes. Subscribe to each requested symbol on one connection rather than
    opening one connection per symbol or depending on an authenticated account
    socket.
    """
    unique_symbols = list(dict.fromkeys(
        str(symbol).strip() for symbol in symbols if str(symbol).strip()
    ))
    if not unique_symbols:
        return {}, 0

    endpoint = getattr(settings, "DERIV_PUBLIC_WS_URL", "").strip()
    if not endpoint:
        raise BrokerConnectionError("DERIV_PUBLIC_WS_URL is not configured")

    started = time.monotonic()
    req_to_symbol = {
        index: symbol for index, symbol in enumerate(unique_symbols, start=1)
    }
    symbol_set = set(unique_symbols)
    results = {}
    deadline = started + max(LIVE_TICK_SCAN_TIMEOUT_SECONDS, 12.0)

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
                await ws.send(json.dumps({
                    "ticks": symbol,
                    "subscribe": 1,
                    "req_id": req_id,
                }))

            while len(results) < len(symbol_set):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=min(2.0, remaining)
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    continue

                if payload.get("error"):
                    continue
                if payload.get("msg_type") != "tick":
                    continue

                tick = payload.get("tick") or {}
                symbol = str(
                    tick.get("symbol")
                    or req_to_symbol.get(payload.get("req_id"))
                    or ""
                )
                if symbol not in symbol_set:
                    continue

                quote = _as_float(tick.get("quote"))
                epoch = _as_float(tick.get("epoch"))
                if quote is None or epoch is None:
                    continue

                results[symbol] = tick
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
        raise BrokerConnectionError(
            "Deriv public live market data is temporarily unavailable"
        ) from exc

    return results, round((time.monotonic() - started) * 1000, 1)


def _revise_signal(signal, live_tick, now, market, account):
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    baseline_direction = str(signal.signal or "HOLD").upper()
    base_confidence = max(0.0, min(100.0, _as_float(signal.confidence) or 0.0))
    analysis_age = max(0, int((now - signal.timestamp).total_seconds()))
    live_epoch = int(live_tick.get("epoch"))
    live_age = max(0, int(time.time()) - live_epoch)
    live_price = _as_float(live_tick.get("quote"))
    entry = _as_float(signal.entry_price)
    revised = base_confidence
    evidence = ["analysis_baseline_loaded", "deriv_public_live_tick"]
    status = "LIVE_REVIEW"
    direction = baseline_direction
    if analysis_age > ANALYSIS_BASELINE_MAX_AGE_SECONDS:
        revised = min(revised, 50.0); status = "ANALYSIS_STALE"; direction = "HOLD"; evidence.append("analysis_baseline_stale")
    elif live_age > LIVE_TICK_MAX_AGE_SECONDS:
        revised = min(revised, 45.0); status = "LIVE_DATA_STALE"; direction = "HOLD"; evidence.append("live_tick_stale")
    elif baseline_direction in {"BUY", "SELL"} and live_price is not None and entry is not None:
        favorable = (baseline_direction == "BUY" and live_price >= entry) or (baseline_direction == "SELL" and live_price <= entry)
        revised = round((base_confidence * 0.80) + ((100.0 if favorable else 0.0) * 0.20), 2)
        if favorable: evidence.append("live_price_confirms_analysis_entry_side")
        else: direction = "HOLD"; status = "LIVE_CONFIRMATION_FAILED"; evidence.append("live_price_conflicts_with_analysis_entry_side")
    elif baseline_direction in {"BUY", "SELL"}:
        evidence.append("analysis_entry_price_unavailable")
    threshold = _as_float(metadata.get("live_confidence_threshold")) or DEFAULT_CONFIDENCE_THRESHOLD
    execution_ready = direction in {"BUY", "SELL"} and revised >= threshold and status == "LIVE_REVIEW"
    if not execution_ready and direction in {"BUY", "SELL"}: status = "LIVE_CONFIDENCE_BELOW_GATE"
    return {
        "analysis_signal_id": signal.id, "analysis_timestamp": signal.timestamp.isoformat(), "analysis_age_seconds": analysis_age,
        "baseline_direction": baseline_direction, "baseline_confidence": round(base_confidence, 2), "direction": direction,
        "confidence": round(revised, 2), "live_confidence_threshold": round(threshold, 2), "execution_ready": execution_ready,
        "status": status, "evidence": evidence, "entry_price": str(signal.entry_price) if signal.entry_price is not None else None,
        "stop_loss": str(signal.stop_loss) if signal.stop_loss is not None else None, "take_profit": str(signal.take_profit) if signal.take_profit is not None else None,
        "strategy": signal.strategy.name, "strategy_version": signal.strategy.version, "timeframe": _analysis_timeframe(signal),
        "analysis_metadata": metadata, "trade_context": _trade_context(signal, market, account),
        "live": {"price": live_price, "bid": _as_float(live_tick.get("bid")), "ask": _as_float(live_tick.get("ask")), "epoch": live_epoch, "age_seconds": live_age, "source": "deriv_public_websocket"},
    }


def strategy_signals(request):
    """Return broker-sourced signal data without HTML login redirects."""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required to read live signals."}, status=401)
    account = _selected_deriv_account(request)
    if account is None:
        return JsonResponse({"status": "error", "code": "DERIV_ACCOUNT_REQUIRED", "message": "Connect and select a Deriv account before reading live signals."}, status=409)
    account_credentials_valid = account.token_status == "active" and not account.is_token_expired
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
    try:
        live_ticks, feed_latency_ms = asyncio.run(_live_deriv_ticks(symbols))
    except BrokerConnectionError as exc:
        return JsonResponse({"status": "error", "code": "DERIV_LIVE_FEED_FAILED", "message": str(exc)}, status=502)
    except Exception:
        return JsonResponse({"status": "error", "code": "DERIV_LIVE_FEED_FAILED", "message": "The Deriv public live market-data feed could not be established."}, status=502)
    baselines = _analysis_baselines(request, symbols, timeframe, account=account)
    now = timezone.now(); rows = []
    for market in markets:
        live_tick = live_ticks.get(market.symbol); baseline = baselines.get(market.symbol)
        row = {"symbol": market.symbol, "instrument": market.display_name, "display_name": market.display_name, "market": market.market, "sub_market": market.sub_market, "broker": "deriv", "account_id": account.account_id, "account_type": account.account_type, "timeframe": timeframe, "source": "deriv_public_live"}
        base_context = {"market_type": market.market, "sub_market": market.sub_market, "symbol": market.symbol, "instrument": market.display_name, "trade_type": None, "direction": "HOLD", "contract_type": None, "contract_family": None, "duration": None, "duration_unit": None, "barrier": None, "stake": None, "payout": None, "currency": account.currency, "account_type": account.account_type, "broker": account.broker.name, "timeframe": timeframe}
        if not live_tick:
            row.update({"direction": "HOLD", "confidence": 0, "status": "LIVE_DATA_UNAVAILABLE", "execution_ready": False, "evidence": ["broker_tick_not_received"], "trade_context": base_context})
        elif not baseline:
            live_age = max(0, int(time.time()) - int(live_tick.get("epoch")))
            row.update({"direction": "HOLD", "confidence": 0, "status": "WAITING_FOR_ANALYSIS", "execution_ready": False, "evidence": ["live_tick_received", "no_matching_analysis_baseline"], "live": {"price": _as_float(live_tick.get("quote")), "bid": _as_float(live_tick.get("bid")), "ask": _as_float(live_tick.get("ask")), "epoch": int(live_tick.get("epoch")), "age_seconds": live_age, "source": "deriv_public_websocket"}, "trade_context": base_context})
        else:
            row.update(_revise_signal(baseline, live_tick, now, market, account))
        rows.append(row)
    if not account_credentials_valid:
        for row in rows:
            if row.get("execution_ready"):
                row["execution_ready"] = False
                row["evidence"] = [*row.get("evidence", []), "selected_account_credentials_not_ready_for_execution"]
                row["status"] = "ACCOUNT_AUTH_REQUIRED"

    actionable = [r for r in rows if r.get("execution_ready")]
    live_data_available_count = sum(1 for r in rows if r.get("live"))
    stale_count = sum(1 for r in rows if r.get("status") == "LIVE_DATA_STALE")
    return JsonResponse({"status": "ok", "source": "deriv_public_live", "generated_at": now.isoformat(), "feed_latency_ms": feed_latency_ms, "account": {"id": account.account_id, "type": account.account_type, "currency": account.currency}, "analysis_role": "upstream_baseline_only", "historical_candles_primary": False, "account_trading_enabled": account_credentials_valid, "live_tick_max_age_seconds": LIVE_TICK_MAX_AGE_SECONDS, "analysis_baseline_max_age_seconds": ANALYSIS_BASELINE_MAX_AGE_SECONDS, "count": len(rows), "live_data_available_count": live_data_available_count, "stale_count": stale_count, "actionable_count": len(actionable), "data": rows})
