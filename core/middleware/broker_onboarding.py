"""Enforce broker onboarding only for trading-workspace browser routes.

Account management and operational observability remain available to a signed-in
AlgoBot user before Deriv is connected. Actual trading/API actions must still
enforce their own broker and risk permissions; browser middleware is not an API
authorization boundary.
"""
from django.shortcuts import redirect


class BrokerOnboardingMiddleware:
    """Require an eligible Deriv connection before entering trading pages."""

    EXEMPT_PREFIXES = (
        "/admin/", "/static/", "/media/", "/health/",
        "/login/", "/register/", "/logout/", "/accounts/login/",
        "/verify-email/", "/forgot-password/", "/reset-password/",
        "/account/identity/", "/account/google/unlink/", "/auth/google/",
        "/brokers/marketplace/", "/brokers/connect/", "/callback/", "/webhooks/", "/payments/",
        "/billing/", "/saas/", "/developer/", "/api/",
    )

    # These pages depend on a live broker connection to perform trading.
    # Settings/profile and monitoring pages remain usable during onboarding.
    PROTECTED_BROWSER_PREFIXES = (
        "/dashboard/", "/markets/", "/market-scanner/", "/strategies/",
        "/trading/", "/backtesting/", "/predictions/", "/model-lab/",
        "/performance/", "/orders/", "/positions/", "/signals/",
        "/portfolio/", "/risk/", "/trade-history/",
        "/analysis/", "/smart-money/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or "/"
        if path == "/" or any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        if not any(path.startswith(prefix) for prefix in self.PROTECTED_BROWSER_PREFIXES):
            return self.get_response(request)

        # Import lazily to avoid app-loading and middleware import cycles.
        from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email
        if not has_verified_account_email(user):
            return redirect("verify_email_page")
        if has_authorized_broker_connection(user):
            return self.get_response(request)

        requested = request.get_full_path()
        if requested.startswith("/") and not requested.startswith("//") and "\\\\" not in requested:
            request.session["broker_onboarding_next"] = requested
        return redirect("broker_marketplace_page")
