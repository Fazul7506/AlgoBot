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


def _resolve_active_account(user, session=None, broker_type=None):
    qs = connected_accounts(user)
    if broker_type:
        qs = qs.filter(broker__broker_type=broker_type)

    selected_id = session.get(SESSION_KEY) if session is not None else None
    if selected_id:
        selected = qs.filter(pk=selected_id).first()
        if selected and _has_known_environment(selected):
            return selected
        # A stale explicit selection must fail closed across DEMO/REAL boundaries.
        session.pop(SESSION_KEY, None)
        if hasattr(session, "modified"):
            session.modified = True
        return None

    # Read-only consumers may use the user's default account when no explicit
    # browser selection exists. This fallback is never permission to execute trades.
    return qs.order_by("-last_synced_at", "-id").first()


def get_active_account(user, request=None, broker_type=None):
    """Resolve the active account from an HTTP request's server-side session."""
    return _resolve_active_account(user, _session(request), broker_type)


def get_active_account_for_session(user, session=None, broker_type=None):
    """Resolve the active account from an explicit Django session mapping.

    Channels consumers use this entry point so their account context follows
    the same authenticated session authority as HTTP views.
    """
    return _resolve_active_account(user, session, broker_type)


def require_active_account(user, request):
    account = get_active_account(user, request=request)
    if not account:
        raise ValueError("No connected broker account is available for this request.")
    if not _has_known_environment(account):
        raise ValueError("The broker account environment is unknown; trading is blocked until DEMO/REAL is verified.")
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
