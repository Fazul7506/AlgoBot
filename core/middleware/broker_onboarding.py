"""Enforce broker onboarding across authenticated browser routes.

The broker callback, broker-management screens, authentication recovery flows,
health checks, webhooks, static assets, and Django admin remain reachable so
users can complete setup and operators can manage the service. API requests get
a machine-readable denial rather than an HTML redirect.
"""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class BrokerOnboardingMiddleware:
    """Do not expose authenticated workspace pages before a usable broker link."""

    EXEMPT_PREFIXES = (
        "/admin/", "/static/", "/media/", "/health/",
        "/login/", "/register/", "/logout/", "/accounts/login/",
        "/verify-email/", "/forgot-password/", "/reset-password/",
        "/account/identity/", "/auth/google/",
        "/brokers/connect/", "/brokers/callback/", "/brokers/marketplace/", "/callback/",
        # Broker catalog, connection status/sync, and recovery actions remain
        # available so a user can complete or repair the required connection.
        "/api/brokers/", "/api/broker-health/", "/api/deriv/",
        "/api/auth/logout/", "/api/auth/change-password/",
        "/webhooks/", "/payments/callback/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path_info or "/"
        if not user or not user.is_authenticated:
            return self.get_response(request)
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        if path == "/":
            return self.get_response(request)

        # Import lazily to avoid app-loading and middleware import cycles.
        from core.broker_onboarding import has_authorized_broker_connection
        if has_authorized_broker_connection(user):
            return self.get_response(request)

        if path.startswith("/api/"):
            return JsonResponse({
                "detail": "Connect and verify a supported broker before accessing workspace features.",
                "code": "broker_setup_required",
                "next_url": reverse("broker_marketplace_page"),
            }, status=403)

        return redirect("broker_marketplace_page")
