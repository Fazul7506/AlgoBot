from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from django.utils import timezone

from apps.brokers.models import BrokerAccount
from apps.execution.models import Order as ExecutionOrder
from apps.risk.repositories import RiskRepository
from apps.risk.services import RiskService


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _decimal(value, default=ZERO):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return default


def _money(value, places="0.00000001"):
    return _decimal(value).quantize(Decimal(places), rounding=ROUND_DOWN)


def _account_type(account: BrokerAccount) -> str:
    return account.account_type or "unknown"


def build_account_risk_context(user, account: BrokerAccount, *, signal=None, confidence=None, volatility=None):
    """Build broker-account-aware sizing context without inventing broker values.

    Balance/equity/margin/free-margin are sourced from the selected BrokerAccount,
    which is refreshed from the broker by the caller when a fresh context is
    requested. Risk limits come from the user's persisted RiskProfile. The
    resulting amount is a risk budget/stake cap, not a promise of maximum loss:
    the exact monetary risk depends on the concrete Deriv contract and proposal.
    """
    profile = RiskRepository().profile_for_user(user)
    today = timezone.localdate()
    daily_orders = ExecutionOrder.objects.filter(
        user=user,
        broker_account=account,
        created_at__date=today,
    )
    realized_loss = ZERO
    open_stake = ZERO
    for order in daily_orders.only("status", "stake", "broker_response"):
        payload = order.broker_response or {}
        profit = _decimal(payload.get("profit", payload.get("pnl")))
        if profit < ZERO:
            realized_loss += abs(profit)
    open_statuses = {"draft", "validated", "queued", "sent", "accepted", "executed"}
    open_orders = ExecutionOrder.objects.filter(
        user=user,
        broker_account=account,
        status__in=open_statuses,
    ).only("stake")
    open_stake = sum((_decimal(o.stake) for o in open_orders), ZERO)

    balance = _decimal(account.balance)
    equity = _decimal(account.equity) if account.equity else balance
    free_margin = _decimal(account.free_margin) if account.free_margin else None
    margin = _decimal(account.margin) if account.margin else None
    available_funds = free_margin if free_margin is not None else balance

    max_risk_fraction = max(ZERO, _decimal(profile.max_risk_per_trade, Decimal("0.02")))
    daily_loss_fraction = max(ZERO, _decimal(profile.max_daily_loss, Decimal("0.04")))
    exposure_fraction = max(ZERO, _decimal(profile.max_exposure, Decimal("0.35")))

    risk_budget = balance * max_risk_fraction
    daily_limit = balance * daily_loss_fraction
    daily_remaining = max(ZERO, daily_limit - realized_loss)
    exposure_limit = balance * exposure_fraction
    exposure_remaining = max(ZERO, exposure_limit - open_stake)

    candidates = [
        ("per_trade_risk_budget", risk_budget),
        ("daily_loss_remaining", daily_remaining),
        ("exposure_remaining", exposure_remaining),
        ("available_funds", max(ZERO, available_funds)),
    ]
    recommended_stake = max(ZERO, min(value for _, value in candidates))

    # Confidence/regime only tighten the recommendation; they never increase the
    # persisted user risk limit. This is deliberately transparent and testable.
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

    risk_score = RiskService().score(
        volatility=Decimal("0.8") if regime in {"high", "extreme"} else Decimal("0.25") if regime == "normal" else Decimal("0.1"),
        exposure=(open_stake / balance) if balance else ZERO,
        drawdown=ZERO,
        correlation=ZERO,
        margin=(margin / balance) if margin is not None and balance else ZERO,
        market_conditions=ZERO,
        strategy_confidence=(confidence_value / HUNDRED) if confidence is not None else Decimal("1"),
    )

    return {
        "broker": account.broker.name,
        "broker_type": account.broker.broker_type,
        "account_id": account.account_id,
        "account_pk": account.pk,
        "account_type": _account_type(account),
        "currency": account.currency,
        "balance": _money(balance),
        "equity": _money(equity),
        "margin": _money(margin),
        "free_margin": _money(free_margin) if free_margin is not None else None,
        "available_funds": _money(available_funds),
        "risk_profile": profile.risk_level,
        "max_risk_per_trade": str(max_risk_fraction),
        "risk_budget": _money(risk_budget),
        "daily_loss_limit": _money(daily_limit),
        "realized_loss_today": _money(realized_loss),
        "daily_loss_remaining": _money(daily_remaining),
        "max_exposure": _money(exposure_limit),
        "open_stake_exposure": _money(open_stake),
        "exposure_remaining": _money(exposure_remaining),
        "confidence": str(confidence_value),
        "confidence_multiplier": str(confidence_multiplier),
        "recommended_stake": _money(adjusted_stake),
        "risk_score": risk_score,
        "risk_label": RiskService().label(risk_score),
        "sizing_basis": "selected broker account balance + persisted risk profile + current exposure + daily loss + live analysis confidence",
        "risk_disclaimer": "Recommended stake is a capped risk budget. Exact loss/payout is broker-contract dependent and requires a concrete Deriv proposal.",
        "signal": str(signal or ""),
    }
