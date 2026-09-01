"""Server-side subscription enforcement for API/tool usage."""
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

    @classmethod
    def _requires_authenticated_user(cls, request):
        """Protect state-changing AI/order endpoints from AnonymousUser failures."""
        method = request.method.upper()
        if method not in EXECUTION_METHODS:
            return False
        return request.path.startswith(("/api/ai/", "/api/predictions/", "/api/orders/")) or cls._is_execution_request(request)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_api = request.path.startswith("/api/")
        is_authenticated = bool(getattr(request.user, "is_authenticated", False))

        # Never let an anonymous request reach billing DB queries. State-changing
        # AI/order/execution calls return a deterministic 401 instead of a 500
        # caused by trying to persist AnonymousUser into a User FK.
        if is_api and self._requires_authenticated_user(request) and not is_authenticated:
            return JsonResponse(
                {"detail": "Authentication credentials were not provided.", "code": "authentication_required"},
                status=401,
            )

        if not is_api or not is_authenticated:
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
                return JsonResponse(
                    rate_limit_response_data(request.user, metric, "day", current, limit),
                    status=429,
                    headers={"Retry-After": "86400"},
                )

        response = self.get_response(request)
        response["X-AlgoBot-Plan"] = effective_plan(request.user).key
        response["X-AlgoBot-Quota-Metric"] = metric
        return response
