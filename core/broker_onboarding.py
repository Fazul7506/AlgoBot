"""Mandatory broker onboarding checks for browser-authenticated users.

Only a provider-verified, active Deriv connection qualifies as completed onboarding.
A local login or OAuth callback alone is never evidence of broker authorization.
"""
from django.utils import timezone

from apps.brokers.models import BrokerAccount


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
    return any(
        (account.expires_at is None or account.expires_at > now)
        and account.is_connection_eligible
        for account in accounts
    )


def post_auth_destination(user, requested_destination=""):
    """Force users without a verified broker connection through broker setup."""
    from django.urls import reverse

    if not has_authorized_broker_connection(user):
        return reverse("broker_marketplace_page")
    return requested_destination or reverse("dashboard_page")
