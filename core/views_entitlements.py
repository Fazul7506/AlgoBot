from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from core.billing_entitlements import PLAN_ENTITLEMENTS, entitlement_payload


@login_required

def billing_entitlements(request):
    return JsonResponse({
        "current": entitlement_payload(request.user),
        "plans": {
            key: {
                "name": value.name,
                "api_daily": value.api_daily,
                "api_per_minute": value.api_per_minute,
                "strategies": value.strategies,
                "backtests_daily": value.backtests_daily,
                "predictions_daily": value.predictions_daily,
                "orders_daily": value.orders_daily,
                "broker_accounts": value.broker_accounts,
                "automations": value.automations,
                "live_trading": value.live_trading,
                "advanced_ai": value.advanced_ai,
                "priority": value.priority,
                "support": value.support,
            }
            for key, value in PLAN_ENTITLEMENTS.items()
        },
    })
