"""Mandatory broker onboarding checks for browser-authenticated users.

Only a provider-verified, active Deriv connection qualifies as completed onboarding.
A local login or OAuth callback alone is never evidence of broker authorization.
"""
import logging

from django.utils import timezone

from apps.brokers.models import BrokerAccount

logger = logging.getLogger("broker_onboarding")


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

