from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.brokers.models import BrokerAccount, ExecutionReport


@login_required
def trade_history_page(request):
    """Render the broker-backed trade journal without exposing another user's records."""
    accounts = BrokerAccount.objects.filter(user=request.user).select_related('broker')
    connected_accounts = [account for account in accounts if account.is_connection_eligible]
    execution_count = ExecutionReport.objects.filter(order__user=request.user).count()
    return render(
        request,
        'core/trade_history.html',
        {
            'broker_accounts': accounts,
            'connected_accounts': connected_accounts,
            'execution_count': execution_count,
            'has_broker_connection': bool(connected_accounts),
        },
    )
