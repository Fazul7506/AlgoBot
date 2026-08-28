"""Server-side subscription enforcement for API/tool usage.

The browser dashboard is a first-party application, not an external API client.
Read-only dashboard/terminal requests must not consume the user's public API
quota; live state is delivered over authenticated WebSockets where possible.
Mutation/resource quotas remain enforced server-side.
"""
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

        # GET/HEAD/OPTIONS are read-only application data access. Counting
        # these against the public API allowance made a 30-second dashboard
        # refresh consume the Free plan's daily quota even while the user was
        # merely looking at their account. Public API/resource mutations remain
        # metered below.
        read_only = request.method.upper() in {"GET", "HEAD", "OPTIONS"}
        if read_only:
            response = self.get_response(request)
            response["X-AlgoBot-Plan"] = effective_plan(request.user).key
            response["X-AlgoBot-Quota-Metric"] = "read_only"
            return response

        for window, retry in (("day", "86400"), ("minute", "60")):
            allowed, current, limit = check(request.user, "api_calls", 1, window)
            if not allowed:
                return JsonResponse(rate_limit_response_data(request.user, "api_calls", window, current, limit), status=429, headers={"Retry-After": retry})

        metric = "api_calls"
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
