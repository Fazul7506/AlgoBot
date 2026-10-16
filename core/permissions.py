"""DRF permission that enforces broker onboarding after API authentication.

This runs after DRF has authenticated session or bearer-token requests, unlike
Django middleware which cannot see a JWT-authenticated principal.
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email


class BrokerOnboardingRequired(BasePermission):
    message = "Connect and verify your broker before accessing workspace or trading APIs."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not has_verified_account_email(request.user):
            raise PermissionDenied({
                "detail": "Verify your AlgoBot email before accessing protected workspace or trading APIs.",
                "code": "email_verification_required",
                "next_url": "/verify-email/",
            })
        if has_authorized_broker_connection(request.user):
            return True
        raise PermissionDenied({
            "detail": self.message,
            "code": "broker_setup_required",
            "next_url": "/brokers/marketplace/",
        })
