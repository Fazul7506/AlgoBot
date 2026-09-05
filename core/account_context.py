"""Authoritative authenticated-user broker account context.

The server-side session is authoritative. The browser may persist the last selected
account for UX, but every requested account is revalidated against the authenticated
user before it becomes active.
"""
from apps.brokers.models import BrokerAccount

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


def _requested_id(request):
    if request is None:
        return None
    # This module is shared by normal Django HttpRequest/WSGI views and DRF
    # requests. Django HttpRequest exposes GET; DRF also exposes the same query
    # data through GET while adding query_params on its Request wrapper. Using
    # GET here keeps the authoritative resolver valid for both request types.
    return request.META.get(REQUEST_HEADER) or request.GET.get(REQUEST_PARAM)


def get_active_account(user, request=None, broker_type=None):
    """Resolve the authenticated user's explicitly requested/session account."""
    qs = connected_accounts(user)
    if broker_type:
        qs = qs.filter(broker__broker_type=broker_type)

    requested_id = _requested_id(request)
    if requested_id:
        selected = qs.filter(pk=requested_id).first()
        if selected:
            return selected

    selected_id = request.session.get(SESSION_KEY) if request is not None else None
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
    request.session[SESSION_KEY] = account.pk
    request.session.modified = True
    return account


def clear_selected_account(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
