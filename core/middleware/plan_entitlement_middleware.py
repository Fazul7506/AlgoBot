"""Server-side subscription enforcement for API/tool usage.

The browser never decides whether a user is entitled to a feature. This
middleware applies the same limits to web, mobile, API and direct HTTP clients.
"""
from __future__ import annotations

from django.http import JsonResponse

from core.billing_entitlements import check, effective_plan, rate_limit_response_data


class PlanEntitlementMiddleware:
    FEATURE_PATHS = (
        ("backtests", ("/api/backtesting/", "/api/strategies/")),
        ("predictions", ("/api/ai/", "/api/predictions/")),
        ("orders", ("/api/orders/",)),
        ("broker_accounts", ("/api/brokers/connect/", "/api/brokers/disconnect/")),
        ("automations", ("/api/automation/",)),
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_api(request):
        return request.path.startswith("/api/")

    @staticmethod
    def _is_mutation(request):
        return request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}

    def __call__(self, request):
        if not self._is_api(request) or not getattr(request.user, "is_authenticated", False):
            return self.get_response(request)

        metric = "api_calls"
        window = "day"
        for candidate, prefixes in self.FEATURE_PATHS:
            if any(request.path.startswith(prefix) for prefix in prefixes) and self._is_mutation(request):
                metric = candidate
                break

        # Reads remain available, but the general API quota still applies.
        if metric == "api_calls" and not self._is_mutation(request):
            window = "day"

        allowed, current, limit = check(request.user, metric, 1, window)
        if not allowed:
            payload = rate_limit_response_data(request.user, metric, window, current, limit)
            return JsonResponse(payload, status=429, headers={"Retry-After": "86400" if window == "day" else "60"})

        # Enterprise live access is still subject to the platform's existing
        # ALLOW_LIVE_TRADING and broker/risk gates. This entitlement only adds
        # the subscription-level gate; it never bypasses safety controls.
        if metric == "orders" and effective_plan(request.user).live_trading is False:
            # Paper/demo orders remain available. Real-money orders are rejected
            # explicitly in the execution layer when their account is real.
            request._algobot_live_entitlement = False

        response = self.get_response(request)
        response["X-AlgoBot-Plan"] = effective_plan(request.user).key
        response["X-AlgoBot-Quota-Metric"] = metric
        return response
