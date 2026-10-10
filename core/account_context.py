""""Authoritative authenticated-user broker account context.

The server-side session is the only active-account authority for browser/API
requests. Client-supplied account IDs are never interpreted as active context.
Account selection happens only through the authenticated account-select action.
"""
from apps.brokers.models import BrokerAccount

SESSION_KEY = "active_broker_account_id"

def connected_accounts(user):
    return (
        BrokerAccount.objects.filter(
            user=user,
            status="active",
            broker__status="active",
            connections__status="connected",
        )
        .select_related("broker")
        .distinct()
    )


def _session(request):
    """Return a session mapping when session middleware is installed."""
    return getattr(request, "session", None) if request is not None else None


def _has_known_environment(account):
    """Require explicit DEMO/REAL metadata for Deriv execution context."""
    return account.broker.broker_type != "deriv" or account.account_type in {"demo", "real"}


def get_active_account(user, request=None, broker_type=None):
    """Resolve the authenticated user's server-side active broker account.

    Request headers and query parameters are transport metadata, not account
    authority. A stale or ineligible explicit session selection is cleared and
    returns no account; it must never silently route the request to another
    connected account. Requests without a browser session retain the existing
    default-account behavior for background consumers.
    """
    qs = connected_accounts(user)
    if broker_type:
        qs = qs.filter(broker__broker_type=broker_type)

    session = _session(request)
    selected_id = session.get(SESSION_KEY) if session is not None else None
    if selected_id:
        selected = qs.filter(pk=selected_id).first()
        if selected and _has_known_environment(selected):
            return selected
        # The explicitly selected account is no longer eligible. Clear the
        # stale selection and fail closed instead of silently using another
        # account, especially across DEMO/REAL boundaries.
        session.pop(SESSION_KEY, None)
        session.modified = True
        return None

    for account in qs.order_by("-last_synced_at", "-id"):
        if _has_known_environment(account):
            return account
    return None


def require_active_account(user, request):
    account = get_active_account(user, request=request)
    if not account:
        raise ValueError("No connected broker account is available for this request.")
    return account


def select_account(request, account):
    if not account or account.user_id != request.user.id:
        raise ValueError("Account does not belong to the authenticated user.")
    if not account.is_connection_eligible or not _has_known_environment(account):
        raise ValueError("The selected broker account is not connected, ready, or has an unknown environment.")
    session = _session(request)
    if session is None:
        raise ValueError("Account selection requires an authenticated browser session.")
    session[SESSION_KEY] = account.pk
    session.modified = True
    return account


def clear_selected_account(request):
    session = _session(request)
    if session is None:
        return
    session.pop(SESSION_KEY, None)
    session.modified = True
