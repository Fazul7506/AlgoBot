"""Server-side subscription enforcement for API/tool usage."""
from __future__ import annotations

from django.http import JsonResponse
from core.billing_entitlements import check, effective_plan, rate_limit_response_data


class PlanEntitlementMiddleware:
    FEATURE_PATHS = (
        ("backtests", ("/api/backtesting/", "/api/strategies/")),
        ("predictions", ("/api/ai/", "/api/predictions/")),
        ("orders", ("/api/orders/",)),
        ("automations", ("/api/automation/",)),
    )
    BACKTEST_ACTIONS = ("/backtest", "/compare", "/optimize")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/") or not getattr(request.user, "is_authenticated", False):
            return self.get_response(request)

        # General API capacity applies to authenticated API calls. Resource
        # count quotas (for example broker accounts) are enforced when a
        # resource is created, never on connect/disconnect/read/sync actions.
        for window, retry in (("day", "86400"), ("minute", "60")):
            allowed, current, limit = check(request.user, "api_calls", 1, window)
            if not allowed:
                return JsonResponse(rate_limit_response_data(request.user, "api_calls", window, current, limit), status=429, headers={"Retry-After": retry})

        mutation = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        metric = "api_calls"
        if mutation:
            for candidate, prefixes in self.FEATURE_PATHS:
                if any(request.path.startswith(prefix) for prefix in prefixes):
                    if candidate == "backtests" and request.path.startswith("/api/strategies/") and not any(x in request.path for x in self.BACKTEST_ACTIONS):
                        continue
                    metric = candidate
                    break

        if metric != "api_calls":
            allowed, current, limit = check(request.user, metric, 1, "day")
            if not allowed:
                return JsonResponse(rate_limit_response_data(request.user, metric, "day", current, limit), status=429, headers={"Retry-After": "86400"})

        response = self.get_response(request)
        response["X-AlgoBot-Plan"] = effective_plan(request.user).key
        response["X-AlgoBot-Quota-Metric"] = metric
        return response
