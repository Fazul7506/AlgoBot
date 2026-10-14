"""Authentication helpers for browser-facing APIs.

JWT authentication also enforces mandatory broker onboarding on protected API
routes. Broker management and authentication endpoints remain available so a
new user can complete setup without getting trapped outside the application.
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.broker_onboarding import has_authorized_broker_connection


class BrowserSessionAuthentication(SessionAuthentication):
    """Authenticate browser sessions with Django/DRF CSRF protection."""

    pass


class BrokerGateJWTAuthentication(JWTAuthentication):
    """Reject JWT-authenticated workspace/API calls until broker setup is verified."""

    EXEMPT_PREFIXES = (
        "/api/auth/",
        "/api/brokers/",
        "/api/broker-health/",
        "/api/deriv/",
        "/health/",
        "/webhooks/",
        "/payments/",
    )

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        path = request.path_info or "/"
        if not any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            if not has_authorized_broker_connection(user):
                raise PermissionDenied({
                    "detail": "Connect and verify a supported broker before accessing workspace or trading APIs.",
                    "code": "broker_setup_required",
                    "next_url": "/brokers/marketplace/",
                })
        return user, validated_token
