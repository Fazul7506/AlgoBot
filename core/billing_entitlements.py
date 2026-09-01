"""Live subscription entitlements and metering policy."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict
from django.db.models import Q
from django.utils import timezone
from core.models import AuditLog, Subscription

@dataclass(frozen=True)
class PlanEntitlement:
    key: str; name: str; api_daily: int; api_per_minute: int; strategies: int; backtests_daily: int; predictions_daily: int; orders_daily: int; broker_accounts: int; automations: int; live_orders_daily: int; live_trading: bool; advanced_ai: bool; priority: str; support: str

PLAN_ENTITLEMENTS: Dict[str, PlanEntitlement] = {
    "FREE": PlanEntitlement("FREE","Free",250,30,1,3,25,10,1,1,5,True,False,"standard","community"),
    "BASIC": PlanEntitlement("BASIC","Basic",5000,120,5,50,250,100,2,5,25,True,True,"priority","standard"),
    "PRO": PlanEntitlement("PRO","Pro",25000,300,25,500,2000,1000,5,25,250,True,True,"highest","priority"),
    "ENTERPRISE": PlanEntitlement("ENTERPRISE","Enterprise",250000,1000,250,-1,-1,-1,50,250,-1,True,True,"dedicated","dedicated"),
}
FEATURE_LABELS={"api_calls":"Trading API calls","strategies":"active strategy configurations","backtests":"backtests","predictions":"AI predictions","orders":"orders","broker_accounts":"connected broker accounts","automations":"automation runs","live_orders":"live-money orders"}

# Public API quota is deliberately restricted to broker/trade execution requests.
# Browser reads, dashboard refreshes, market snapshots, signals and ordinary
# application navigation are not part of this meter.
EXECUTION_PATH_PREFIXES = (
    "/api/orders/",
    "/api/trading/execute/",
    "/api/trades/execute/",
    "/api/execution/",
)
EXECUTION_METHODS = ("POST", "PUT", "PATCH")
RESETTABLE_METRICS = {"api_calls", "backtests", "predictions", "orders", "automations", "live_orders"}


def subscription_for(user):
    """Return the user's subscription, never attempting a DB lookup for anonymous users."""
    if not getattr(user, "is_authenticated", False):
        return None
    subscription,_=Subscription.objects.get_or_create(user=user,defaults={"plan":"FREE"})
    return subscription


def effective_plan(user):
    """Return a safe FREE entitlement for anonymous requests.

    Middleware and error-handling paths can legitimately see AnonymousUser.  Billing
    code must never pass that sentinel into a ForeignKey query, which otherwise
    raises ``TypeError: Field 'id' expected a number`` and turns an auth failure
    into an HTTP 500.
    """
    if not getattr(user, "is_authenticated", False):
        return PLAN_ENTITLEMENTS["FREE"]
    subscription=subscription_for(user)
    key=str(subscription.plan or "FREE").upper()
    if key not in PLAN_ENTITLEMENTS: key="FREE"
    if key!="FREE" and (not subscription.is_active or (subscription.expires_at and subscription.expires_at<=timezone.now())): key="FREE"
    return PLAN_ENTITLEMENTS[key]

def _start(window):
    now=timezone.now(); return now.replace(hour=0,minute=0,second=0,microsecond=0) if window=="day" else now.replace(second=0,microsecond=0)

def reset_at(window="day"):
    start = _start(window)
    return start + (timedelta(days=1) if window == "day" else timedelta(minutes=1))

def _audit_count(user,start,prefixes=None,methods=None):
    qs=AuditLog.objects.filter(user=user,created_at__gte=start)
    if prefixes:
        q=Q()
        for prefix in prefixes: q|=Q(path__startswith=prefix)
        qs=qs.filter(q)
    if methods: qs=qs.filter(method__in=methods)
    return qs.count()

def usage(user,metric,window="day"):
    start=_start(window)
    if metric=="api_calls": return _audit_count(user,start,EXECUTION_PATH_PREFIXES,EXECUTION_METHODS)
    if metric=="backtests": return _audit_count(user,start,["/api/backtesting/","/api/strategies/"],["POST"])
    if metric=="predictions": return _audit_count(user,start,["/api/ai/","/api/predictions/"],["POST"])
    if metric in ("orders","live_orders"): return _audit_count(user,start,["/api/orders/"],["POST"])
    if metric=="automations": return _audit_count(user,start,["/api/automation/","/automation/"],["POST"])
    if metric=="broker_accounts":
        try:
            from apps.brokers.models import BrokerAccount
            return BrokerAccount.objects.filter(user=user).count()
        except Exception: return 0
    if metric=="strategies":
        try:
            from apps.strategies.models import StrategyConfiguration
            return StrategyConfiguration.objects.filter(user=user,enabled=True).count()
        except Exception: return 0
    return 0

def limit_for(plan,metric,window="day"):
    if metric=="api_calls": return plan.api_daily if window=="day" else plan.api_per_minute
    return {"strategies":plan.strategies,"backtests":plan.backtests_daily,"predictions":plan.predictions_daily,"orders":plan.orders_daily,"live_orders":plan.live_orders_daily,"broker_accounts":plan.broker_accounts,"automations":plan.automations}.get(metric,-1)

def check(user,metric,amount=1,window="day"):
    plan=effective_plan(user); limit=limit_for(plan,metric,window); current=usage(user,metric,window)
    return (True,current,limit) if limit<0 else (current+amount<=limit,current,limit)

def check_live_order(user): return check(user,"live_orders")

def entitlement_payload(user):
    plan=effective_plan(user); subscription=subscription_for(user)
    if subscription is None:
        return {"plan": plan.key, "name": plan.name, "active": False, "expires_at": None, "priority": plan.priority, "support": plan.support, "features": {"live_trading": True, "advanced_ai": plan.advanced_ai}, "usage": {}, "reset_at": reset_at("day").isoformat(), "reset_policy": {"daily":"Every day at 00:00 UTC", "minute":"Every minute; applies to the trading API-call burst limit", "subscription":"Paid-plan entitlements fall back to FREE when the subscription expires; usage meters reset automatically", "capacity":"Connected broker-account and active-strategy limits are capacity limits, not expiring counters"}}
    items={}
    for metric in ("api_calls","strategies","backtests","predictions","orders","broker_accounts","automations","live_orders"):
        limit=limit_for(plan,metric); current=usage(user,metric); window="day"
        item={"used":current,"limit":None if limit<0 else limit,"unlimited":limit<0,"remaining":None if limit<0 else max(0,limit-current)}
        if metric in RESETTABLE_METRICS:
            item.update({"reset_at":reset_at(window).isoformat(),"reset_window":window})
        else:
            item.update({"reset_at":None,"reset_window":None,"limit_type":"capacity"})
        items[metric]=item
    return {"plan":plan.key,"name":plan.name,"active":bool(subscription.is_active and (not subscription.expires_at or subscription.expires_at>timezone.now())),"expires_at":subscription.expires_at.isoformat() if subscription.expires_at else None,"priority":plan.priority,"support":plan.support,"features":{"live_trading":True,"advanced_ai":plan.advanced_ai},"usage":items,"reset_at":reset_at("day").isoformat(),"reset_policy":{"daily":"Every day at 00:00 UTC","minute":"Every minute; applies to the trading API-call burst limit","subscription":"Paid-plan entitlements fall back to FREE when the subscription expires; usage meters reset automatically","capacity":"Connected broker-account and active-strategy limits are capacity limits, not expiring counters"}}
