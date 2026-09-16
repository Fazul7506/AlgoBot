"""Authoritative authenticated-user broker account context.

The server-side session is authoritative. The browser may persist the last selected
account for UX, but every requested account is revalidated against the authenticated
user before it becomes active.
"""
from django.utils import timezone

from apps.brokers.models import BrokerAccount, BrokerConnection

SESSION_KEY = "active_broker_account_id"
REQUEST_HEADER = "HTTP_X_ALGOBOT_ACCOUNT_ID"
REQUEST_PARAM = "account_id"


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


def _repair_deferred_oauth_connections(user, broker_type=None):
    """Promote only OAuth-verified connections whose websocket check was deferred.

    Older OAuth callbacks persisted these connections as ``degraded`` while
    recording ``oauth_verified=True`` and ``websocket_health=not_checked``.
    That state made an otherwise valid account disappear from the canonical
    connected-account resolver. A later broker heartbeat still owns the real
    health state; this repair only handles the explicit deferred-check marker.
    """
    accounts = BrokerAccount.objects.filter(
        user=user,
        status="active",
        token_status="active",
        broker__status="active",
        credentials__connection_health="not_checked",
        connections__status="degraded",
        connections__heartbeat__oauth_verified=True,
        connections__heartbeat__websocket_health="not_checked",
    )
    if broker_type:
        accounts = accounts.filter(broker__broker_type=broker_type)
    account_ids = list(accounts.values_list("id", flat=True))
    if not account_ids:
        return 0
    return BrokerConnection.objects.filter(
        broker_account_id__in=account_ids,
        status="degraded",
        heartbeat__oauth_verified=True,
        heartbeat__websocket_health="not_checked",
    ).update(status="connected", last_ping=None, connected_at=timezone.now())


def _requested_id(request):
    if request is None:
        return None
    # This module is shared by normal Django HttpRequest/WSGI views and DRF
    # requests. Django HttpRequest exposes GET; DRF also exposes the same query
    # data through GET while adding query_params on its Request wrapper. Using
    # GET here keeps the authoritative resolver valid for both request types.
    return request.META.get(REQUEST_HEADER) or request.GET.get(REQUEST_PARAM)


def _session(request):
    """Return a session mapping when session middleware is installed."""
    return getattr(request, "session", None) if request is not None else None


def get_active_account(user, request=None, broker_type=None):
    """Resolve the authenticated user's explicitly requested/session account."""
    qs = connected_accounts(user)
    if broker_type:
        qs = qs.filter(broker__broker_type=broker_type)

    if not qs.exists():
        _repair_deferred_oauth_connections(user, broker_type=broker_type)
        qs = connected_accounts(user)
        if broker_type:
            qs = qs.filter(broker__broker_type=broker_type)

    requested_id = _requested_id(request)
    if requested_id:
        selected = qs.filter(pk=requested_id).first()
        if selected:
            return selected

    session = _session(request)
    selected_id = session.get(SESSION_KEY) if session is not None else None
    if selected_id:
        selected = qs.filter(pk=selected_id).first()
        if selected:
            return selected

    return qs.order_by("-last_synced_at", "-id").first()


def require_active_account(user, request):
    account = get_active_account(user, request=request)
    if not account:
        raise ValueError("No connected broker account is available for this request.")
    return account


def select_account(request, account):
    if not account or account.user_id != request.user.id:
        raise ValueError("Account does not belong to the authenticated user.")
    if not account.is_connection_eligible:
        raise ValueError("The selected broker account is not connected and ready.")
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
