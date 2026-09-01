"""Authoritative user-selected broker account context.

Selection belongs to the authenticated user's session, not to a broker-level
preference. DEMO and REAL accounts are equally eligible; the broker's verified
account type remains authoritative for execution safety.
"""
from apps.brokers.models import BrokerAccount

SESSION_KEY = 'active_broker_account_id'

def connected_accounts(user):
    return BrokerAccount.objects.filter(user=user,status='active',broker__status='active',connections__status='connected').select_related('broker').distinct()

def get_active_account(user, request=None, broker_type=None):
    qs=connected_accounts(user)
    if broker_type: qs=qs.filter(broker__broker_type=broker_type)
    selected_id=request.session.get(SESSION_KEY) if request is not None else None
    if selected_id:
        selected=qs.filter(pk=selected_id).first()
        if selected: return selected
    return qs.order_by('-last_synced_at','-id').first()

def select_account(request, account):
    if not account or account.user_id != request.user.id: raise ValueError('Account does not belong to the authenticated user.')
    if not account.is_connection_eligible: raise ValueError('The selected broker account is not connected and ready.')
    request.session[SESSION_KEY]=account.pk; request.session.modified=True
    return account

def clear_selected_account(request):
    request.session.pop(SESSION_KEY,None); request.session.modified=True
