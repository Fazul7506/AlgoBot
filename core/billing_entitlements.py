"""Live subscription entitlements and metering policy.

The plan model is intentionally product-specific rather than a copy of any
third-party price sheet. It follows the modern SaaS pattern of a useful Free
tier, materially higher paid limits, separate tool quotas, and enterprise
fair-use capacity. Enforcement is server-side; the UI is only a reflection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Optional

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from core.models import AuditLog, Subscription


@dataclass(frozen=True)
class PlanEntitlement:
    key: str
    name: str
    api_daily: int
    api_per_minute: int
    strategies: int
    backtests_daily: int
    predictions_daily: int
    orders_daily: int
    broker_accounts: int
    automations: int
    live_trading: bool
    advanced_ai: bool
    priority: str
    support: str


# -1 means fair-use/unmetered for that dimension, while burst protection and
# abuse controls still apply. Values are intentionally generous for paid tiers.
PLAN_ENTITLEMENTS: Dict[str, PlanEntitlement] = {
    "FREE": PlanEntitlement("FREE", "Free", 250, 30, 1, 3, 25, 10, 1, 1, False, False, "standard", "community"),
    "BASIC": PlanEntitlement("BASIC", "Basic", 5000, 120, 5, 50, 250, 100, 2, 5, False, True, "priority", "standard"),
    "PRO": PlanEntitlement("PRO", "Pro", 25000, 300, 25, 500, 2000, 1000, 5, 25, True, True, "highest", "priority"),
    "ENTERPRISE": PlanEntitlement("ENTERPRISE", "Enterprise", 250000, 1000, 250, -1, -1, -1, 50, 250, True, True, "dedicated", "dedicated"),
}

FEATURE_LABELS = {
    "api_calls": "API calls",
    "strategies": "active strategy configurations",
    "backtests": "backtests",
    "predictions": "AI predictions",
    "orders": "orders",
    "broker_accounts": "connected broker accounts",
    "automations": "automation runs",
}


def subscription_for(user) -> Subscription:
    subscription, _ = Subscription.objects.get_or_create(user=user, defaults={"plan": "FREE"})
    return subscription


def effective_plan(user) -> PlanEntitlement:
    subscription = subscription_for(user)
    plan = str(subscription.plan or "FREE").upper()
    if plan not in PLAN_ENTITLEMENTS:
        plan = "FREE"
    if plan != "FREE" and (not subscription.is_active or (subscription.expires_at and subscription.expires_at <= timezone.now())):
        return PLAN_ENTITLEMENTS["FREE"]
    return PLAN_ENTITLEMENTS[plan]


def _day_start():
    now = timezone.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _minute_start():
    now = timezone.now()
    return now.replace(second=0, microsecond=0)


def _audit_count(user, start, path_prefixes=None, methods=None) -> int:
    qs = AuditLog.objects.filter(user=user, created_at__gte=start)
    if path_prefixes:
        path_q = Q()
        for prefix in path_prefixes:
            path_q |= Q(path__startswith=prefix)
        qs = qs.filter(path_q)
    if methods:
        qs = qs.filter(method__in=methods)
    return qs.count()


def usage(user, metric: str, window: str = "day") -> int:
    start = _day_start() if window == "day" else _minute_start()
    prefixes = None
    methods = None
    if metric == "api_calls":
        prefixes = ["/api/"]
    elif metric == "backtests":
        prefixes = ["/api/backtesting/", "/api/strategies/"]
        methods = ["POST"]
    elif metric == "predictions":
        prefixes = ["/api/ai/", "/api/predictions/"]
        methods = ["POST"]
    elif metric == "orders":
        prefixes = ["/api/orders/"]
        methods = ["POST"]
    elif metric == "automations":
        prefixes = ["/api/automation/", "/automation/"]
        methods = ["POST"]
    elif metric == "broker_accounts":
        try:
            from apps.brokers.models import BrokerAccount
            return BrokerAccount.objects.filter(user=user).count()
        except Exception:
            return 0
    elif metric == "strategies":
        try:
            from apps.strategies.models import StrategyConfiguration
            return StrategyConfiguration.objects.filter(user=user, enabled=True).count()
        except Exception:
            return 0
    return _audit_count(user, start, prefixes, methods)


def limit_for(plan: PlanEntitlement, metric: str, window: str = "day") -> int:
    if metric == "api_calls":
        return plan.api_daily if window == "day" else plan.api_per_minute
    return {
        "strategies": plan.strategies,
        "backtests": plan.backtests_daily,
        "predictions": plan.predictions_daily,
        "orders": plan.orders_daily,
        "broker_accounts": plan.broker_accounts,
        "automations": plan.automations,
    }.get(metric, -1)


def check(user, metric: str, amount: int = 1, window: str = "day") -> tuple[bool, int, int]:
    plan = effective_plan(user)
    limit = limit_for(plan, metric, window)
    if limit < 0:
        return True, usage(user, metric, window), limit
    current = usage(user, metric, window)
    return current + amount <= limit, current, limit


def entitlement_payload(user) -> dict:
    plan = effective_plan(user)
    items = {}
    for metric in ("api_calls", "strategies", "backtests", "predictions", "orders", "broker_accounts", "automations"):
        limit = limit_for(plan, metric)
        current = usage(user, metric)
        items[metric] = {"used": current, "limit": None if limit < 0 else limit, "unlimited": limit < 0, "remaining": None if limit < 0 else max(0, limit - current)}
    subscription = subscription_for(user)
    return {
        "plan": plan.key,
        "name": plan.name,
        "active": bool(subscription.is_active and (not subscription.expires_at or subscription.expires_at > timezone.now())),
        "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
        "priority": plan.priority,
        "support": plan.support,
        "features": {
            "live_trading": plan.live_trading,
            "advanced_ai": plan.advanced_ai,
        },
        "usage": items,
        "reset_at": (_day_start() + timedelta(days=1)).isoformat(),
    }


def rate_limit_response_data(user, metric: str, window: str, current: int, limit: int) -> dict:
    plan = effective_plan(user)
    return {
        "code": "PLAN_LIMIT_REACHED",
        "detail": f"{FEATURE_LABELS.get(metric, metric)} limit reached for {plan.name}.",
        "plan": plan.key,
        "metric": metric,
        "used": current,
        "limit": limit,
        "reset_at": (_day_start() + timedelta(days=1)).isoformat() if window == "day" else (_minute_start() + timedelta(minutes=1)).isoformat(),
        "upgrade_available": plan.key != "ENTERPRISE",
    }
