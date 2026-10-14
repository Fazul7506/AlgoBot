"""Enforce broker onboarding on protected browser workspace routes.

Authentication, account recovery, billing, developer tooling, operations,
broker management, health checks, webhooks, static assets, and Django admin
remain reachable. API authorization is handled by DRF permissions after the
request has been authenticated; this middleware must not pre-empt API views.
"""
from django.shortcuts import redirect


class BrokerOnboardingMiddleware:
    """Require a usable broker connection before protected trading pages."""

    EXEMPT_PREFIXES = (
        "/admin/", "/static/", "/media/", "/health/",
        "/login/", "/register/", "/logout/", "/accounts/login/",
        "/verify-email/", "/forgot-password/", "/reset-password/",
        "/account/identity/", "/account/google/unlink/", "/auth/google/",
        "/brokers/", "/callback/", "/webhooks/", "/payments/",
        "/billing/", "/saas/", "/developer/", "/api/",
    )

    PROTECTED_BROWSER_PREFIXES = (
        "/dashboard/", "/markets/", "/market-scanner/", "/strategies/",
        "/trading/", "/backtesting/", "/predictions/", "/model-lab/",
        "/performance/", "/orders/", "/positions/", "/signals/",
        "/portfolio/", "/risk/", "/trade-history/", "/automation/",
        "/analysis/", "/workflow-templates/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or "/"
        if path == "/" or any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        if not any(path.startswith(prefix) for prefix in self.PROTECTED_BROWSER_PREFIXES):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        # Import lazily to avoid app-loading and middleware import cycles.
        from core.broker_onboarding import has_authorized_broker_connection
        if has_authorized_broker_connection(user):
            return self.get_response(request)

        requested = request.get_full_path()
        if requested.startswith("/") and not requested.startswith("//") and "\\\\" not in requested:
            request.session["broker_onboarding_next"] = requested
        return redirect("broker_marketplace_page")
