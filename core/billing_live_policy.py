"""Live-trading entitlement policy: every plan may trade; plans cap activity."""
from core.billing_entitlements import effective_plan, check_live_order

def check_live_execution(user):
    return check_live_order(user)

def live_policy_payload(user):
    plan = effective_plan(user)
    allowed, used, limit = check_live_order(user)
    return {"enabled": True, "plan": plan.key, "allowed_now": allowed, "used_today": used, "daily_limit": None if limit < 0 else limit, "unlimited": limit < 0}
