"""Server-side subscription enforcement for API/tool usage.

The browser dashboard is a first-party application, not an external API client.
Read-only dashboard/terminal requests must not consume the user's public API
quota; live state is delivered over authenticated WebSockets where possible.
Only requests that actually trigger broker/trade execution consume the generic
API-call allowance. Feature-specific limits remain enforced independently.
"""
from __future__ import annotations

from django.http import JsonResponse
from core.billing_entitlements import (
    EXECUTION_METHODS,
    EXECUTION_PATH_PREFIXES,
    check,
    effective_plan,
    rate_limit_response_data,
)


class PlanEntitlementMiddleware:
    FEATURE_PATHS = (
        ("backtests", ("/api/backtesting/", "/api/strategies/")),
        ("predictions", ("/api/ai/", "/api/predictions/")),
        ("orders", ("/api/orders/",)),
        ("automations", ("/api/automation/",)),
    )
    BACKTEST_ACTIONS = ("/backtest", "/compare", "/optimize")

    @staticmethod
    def _is_execution_request(request):
        method = request.method.upper()
        return method in EXECUTION_METHODS and any(
            request.path.startswith(prefix) for prefix in EXECUTION_PATH_PREFIXES
        )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/") or not getattr(request.user, "is_authenticated", False):
            return self.get_response(request)

        # The generic API allowance is for actual trading/execution triggers,
        # not for dashboard reads, market data, account sync, signals, billing,
        # WebSocket support, or other application plumbing.
        if not self._is_execution_request(request):
            response = self.get_response(request)
            response["X-AlgoBot-Plan"] = effective_plan(request.user).key
            response["X-AlgoBot-Quota-Metric"] = "none"
            return response

        for window, retry in (("day", "86400"), ("minute", "60")):
            allowed, current, limit = check(request.user, "api_calls", 1, window)
            if not allowed:
                return JsonResponse(
                    rate_limit_response_data(request.user, "api_calls", window, current, limit),
                    status=429,
                    headers={"Retry-After": retry},
                )

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
