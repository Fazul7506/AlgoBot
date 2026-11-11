"""Mandatory broker onboarding checks for browser-authenticated users.

Only a provider-verified, active Deriv connection qualifies as completed onboarding.
A local login or OAuth callback alone is never evidence of broker authorization.
"""
import logging
from functools import wraps

from django.http import JsonResponse

from core.account_context import get_active_account

logger = logging.getLogger("broker_onboarding")


def has_verified_account_email(user):
    """Require explicit local email verification before protected workspace access."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not str(getattr(user, "email", "") or "").strip():
        return False
    from core.models import UserProfile
    return UserProfile.objects.filter(user_id=user.pk, email_verified=True).exists()


def has_authorized_broker_connection(user, request=None):
    """Return True only for the explicitly selected, provider-verified Deriv account.

    This deliberately delegates account ownership, credential state, snapshot
    freshness and selection to the single server-side account-context resolver.
    A connected account row without an explicit session selection is not
    sufficient to unlock the trading workspace.
    """
    if not user or not getattr(user, "is_authenticated", False) or request is None:
        return False
    try:
        account = get_active_account(user, request=request, broker_type="deriv")
        return bool(account and account.is_connection_eligible and account.last_synced_at)
    except Exception as exc:
        logger.warning(
            "broker_onboarding_account_context_check_failed",
            extra={"user_id": getattr(user, "pk", None), "error_type": exc.__class__.__name__},
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
        if has_authorized_broker_connection(user, request=request):
            return view_func(request, *args, **kwargs)
        return JsonResponse({
            "detail": "Connect and verify your Deriv account before using trading features.",
            "code": "broker_setup_required",
            "next_url": "/brokers/marketplace/",
        }, status=403)
    return wrapped
