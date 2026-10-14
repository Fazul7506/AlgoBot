"""Mandatory broker onboarding checks for browser-authenticated users.

Only a provider-verified, active Deriv connection qualifies as completed onboarding.
A local login or OAuth callback alone is never evidence of broker authorization.
"""
import logging
from functools import wraps

from django.http import JsonResponse

from django.utils import timezone

from apps.brokers.models import BrokerAccount

logger = logging.getLogger("broker_onboarding")


def has_verified_account_email(user):
    """Require explicit local email verification before protected workspace access."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not str(getattr(user, "email", "") or "").strip():
        return False
    from core.models import UserProfile
    return UserProfile.objects.filter(user_id=user.pk, email_verified=True).exists()


def has_authorized_broker_connection(user):
    """Return True only when this user owns a currently usable Deriv connection."""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    accounts = (
        BrokerAccount.objects.filter(
            user_id=user.pk,
            broker__broker_type="deriv",
            status="active",
            broker__status="active",
            token_status="active",
        )
        .select_related("broker")
        .prefetch_related("connections")
    )
    now = timezone.now()
    for account in accounts:
        if account.expires_at is not None and account.expires_at <= now:
            continue
        try:
            if account.is_connection_eligible:
                return True
        except Exception as exc:
            # Missing/invalid encryption keys or unreadable legacy tokens must
            # fail closed as an incomplete connection, not crash a request.
            logger.warning(
                "broker_onboarding_credential_check_failed",
                extra={
                    "user_id": user.pk,
                    "broker_account_id": account.pk,
                    "error_type": exc.__class__.__name__,
                },
            )
    return False



def require_broker_onboarding(view_func):
    """Django-view decorator for JSON trading endpoints outside DRF.

    The decorator is deliberately separate from authentication middleware so
    broker setup, billing, developer tooling, and account recovery remain usable
    before onboarding is complete.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return JsonResponse({"detail": "Authentication credentials are required.", "code": "not_authenticated"}, status=401)
        if not has_verified_account_email(user):
            return JsonResponse({
                "detail": "Verify your AlgoBot email before using trading features.",
                "code": "email_verification_required",
                "next_url": "/verify-email/",
            }, status=403)
        if has_authorized_broker_connection(user):
            return view_func(request, *args, **kwargs)
        return JsonResponse({
            "detail": "Connect and verify your Deriv account before using trading features.",
            "code": "broker_setup_required",
            "next_url": "/brokers/marketplace/",
        }, status=403)
    return wrapped
