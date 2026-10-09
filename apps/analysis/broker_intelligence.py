from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from django.db.models import Q
from django.utils import timezone

from apps.brokers.models import BrokerAccount, Order as BrokerOrder, Position
from apps.execution.models import BrokerTradeHistory
from apps.risk.repositories import RiskRepository
from apps.risk.services import RiskService


ZERO = Decimal("0")
HUNDRED = Decimal("100")
CLOSED_HISTORY_STATUSES = {"sold", "expired", "closed", "won", "lost", "settled"}
OPEN_ORDER_STATUSES = {"created", "validated", "approved", "queued", "submitted", "pending", "executed", "partially_filled", "filled"}


def _decimal(value, default=ZERO):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else default
    except (TypeError, ValueError, ArithmeticError):
        return default


def _money(value, places="0.00000001"):
    return _decimal(value).quantize(Decimal(places), rounding=ROUND_DOWN)


def _account_type(account: BrokerAccount) -> str:
    return account.account_type or "unknown"


def build_account_risk_context(user, account: BrokerAccount, *, signal=None, confidence=None, volatility=None, broker_data=None):
    """Build a conservative account risk context from broker orders and broker-confirmed history.

    Balance and available-funds inputs are only considered known when the broker
    supplied them or the account has a prior synchronization. BrokerOrder and
    BrokerTradeHistory are the execution records used by this application; the
    legacy apps.execution.Order table is not an authoritative source for them.
    """
    profile = RiskRepository().profile_for_user(user)
    today = timezone.localdate()
    fresh_data = broker_data if isinstance(broker_data, dict) else None

    if fresh_data is not None:
        balance_raw = fresh_data.get("balance")
        equity_raw = fresh_data.get("equity")
        margin_raw = fresh_data.get("margin")
        free_margin_raw = fresh_data.get("free_margin")
    elif account.last_synced_at:
        balance_raw = account.balance
        equity_raw = account.equity
        margin_raw = account.margin
        free_margin_raw = account.free_margin
    else:
        balance_raw = equity_raw = margin_raw = free_margin_raw = None

    balance_known = balance_raw is not None
    balance = _decimal(balance_raw) if balance_known else ZERO
    equity = _decimal(equity_raw) if equity_raw is not None else None
    margin = _decimal(margin_raw) if margin_raw is not None else None
    free_margin = _decimal(free_margin_raw) if free_margin_raw is not None else None

    if free_margin is not None:
        available_funds = max(ZERO, free_margin)
        funds_known = True
    elif balance_known and margin is not None:
        available_funds = max(ZERO, balance - margin)
        funds_known = True
    else:
        available_funds = ZERO
        funds_known = False

    settled_today = BrokerTradeHistory.objects.filter(
        user=user,
        broker_account=account,
        settlement_time__date=today,
    )
    missing_pnl_today = settled_today.filter(profit_loss__isnull=True).exists()
    realized_loss = ZERO
    for trade in settled_today.only("profit_loss"):
        if trade.profit_loss is not None:
            profit = _decimal(trade.profit_loss)
            if profit < ZERO:
                realized_loss += abs(profit)
    daily_loss_known = not missing_pnl_today

    settled_order_ids = BrokerTradeHistory.objects.filter(
        user=user,
        broker_account=account,
        settlement_time__isnull=False,
    ).exclude(broker_order_id__isnull=True).exclude(broker_order_id="").values_list("broker_order_id", flat=True)
    open_orders = BrokerOrder.objects.filter(
        user=user,
        account=account,
        status__in=OPEN_ORDER_STATUSES,
    ).exclude(broker_order_id__in=settled_order_ids).only("stake", "broker_order_id")
    open_positions = Position.objects.filter(account=account, status__in=["open", "active"]).only("stake", "broker_order_id")
    position_order_ids = open_positions.exclude(broker_order_id="").values_list("broker_order_id", flat=True)
    orders_without_position = open_orders.exclude(broker_order_id__in=position_order_ids)
    exposure_unknown = open_positions.filter(stake__isnull=True).exists() or orders_without_position.filter(stake__lte=0).exists()
    open_stake = sum(
        (_decimal(value) for value in open_positions.exclude(stake__isnull=True).values_list("stake", flat=True)),
        ZERO,
    ) + sum(
        (_decimal(value) for value in orders_without_position.values_list("stake", flat=True)),
        ZERO,
    )
    if exposure_unknown:
        open_stake = ZERO

    max_risk_fraction = max(ZERO, _decimal(profile.max_risk_per_trade, Decimal("0.02")))
    daily_loss_fraction = max(ZERO, _decimal(profile.max_daily_loss, Decimal("0.04")))
    exposure_fraction = max(ZERO, _decimal(profile.max_exposure, Decimal("0.35")))
    risk_budget = balance * max_risk_fraction if balance_known else ZERO
    daily_limit = balance * daily_loss_fraction if balance_known else ZERO
    daily_remaining = max(ZERO, daily_limit - realized_loss) if daily_loss_known and balance_known else ZERO
    exposure_limit = balance * exposure_fraction if balance_known else ZERO
    exposure_remaining = max(ZERO, exposure_limit - open_stake) if balance_known and not exposure_unknown else ZERO

    candidates = [risk_budget, daily_remaining, exposure_remaining, available_funds]
    recommended_stake = max(ZERO, min(candidates))
    confidence_value = _decimal(confidence, HUNDRED)
    if confidence_value < Decimal("60"):
        confidence_multiplier = Decimal("0.50")
    elif confidence_value < Decimal("75"):
        confidence_multiplier = Decimal("0.75")
    else:
        confidence_multiplier = Decimal("1.00")
    regime = str(volatility or "").lower()
    if regime in {"high", "extreme"}:
        confidence_multiplier = min(confidence_multiplier, Decimal("0.50"))
    adjusted_stake = min(recommended_stake * confidence_multiplier, recommended_stake)

    inputs_complete = balance_known and funds_known and daily_loss_known and not exposure_unknown
    risk_score = None
    if inputs_complete:
        risk_score = RiskService().score(
            volatility=Decimal("0.8") if regime in {"high", "extreme"} else Decimal("0.25") if regime == "normal" else Decimal("0.1"),
            exposure=(open_stake / balance) if balance else ZERO,
            drawdown=ZERO,
            correlation=ZERO,
            margin=(margin / balance) if margin is not None and balance else ZERO,
            market_conditions=ZERO,
            strategy_confidence=(confidence_value / HUNDRED) if confidence is not None else Decimal("1"),
        )

    issues = []
    if not balance_known:
        issues.append("broker_balance_unavailable")
    if not funds_known:
        issues.append("broker_available_funds_unavailable")
    if not daily_loss_known:
        issues.append("settled_trade_pnl_incomplete")
    if exposure_unknown:
        issues.append("open_exposure_incomplete")

    return {
        "broker": account.broker.name,
        "broker_type": account.broker.broker_type,
        "account_id": account.account_id,
        "account_pk": account.pk,
        "account_type": _account_type(account),
        "currency": account.currency,
        "balance": _money(balance) if balance_known else None,
        "equity": _money(equity) if equity is not None else None,
        "margin": _money(margin) if margin is not None else None,
        "free_margin": _money(free_margin) if free_margin is not None else None,
        "available_funds": _money(available_funds) if funds_known else None,
        "risk_profile": profile.risk_level,
        "max_risk_per_trade": str(max_risk_fraction),
        "risk_budget": _money(risk_budget),
        "daily_loss_limit": _money(daily_limit) if balance_known else None,
        "realized_loss_today": _money(realized_loss) if daily_loss_known else None,
        "daily_loss_remaining": _money(daily_remaining) if daily_loss_known and balance_known else None,
        "max_exposure": _money(exposure_limit) if balance_known else None,
        "open_stake_exposure": _money(open_stake) if not exposure_unknown else None,
        "exposure_remaining": _money(exposure_remaining) if balance_known and not exposure_unknown else None,
        "confidence": str(confidence_value),
        "confidence_multiplier": str(confidence_multiplier),
        "recommended_stake": _money(adjusted_stake),
        "risk_score": risk_score,
        "risk_label": RiskService().label(risk_score) if risk_score is not None else "unavailable",
        "risk_inputs_complete": inputs_complete,
        "risk_data_issues": issues,
        "sizing_basis": "broker account balance + broker-order exposure + broker-confirmed settled trade history + persisted risk profile",
        "risk_disclaimer": "Recommended stake is a capped risk budget, not a promise of maximum loss. If broker balance, settled P/L or open exposure is incomplete, the recommended stake is zero until the missing risk data is available.",
        "signal": str(signal or ""),
    }
