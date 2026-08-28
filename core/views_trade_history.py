from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
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


@login_required
def trade_history_api(request):
    """JSON feed used by the journal; only the authenticated user's executions are returned."""
    qs = ExecutionReport.objects.filter(order__user=request.user).select_related(
        'order', 'order__broker', 'order__account'
    )
    symbol = request.GET.get('symbol', '').strip()
    strategy = request.GET.get('strategy', '').strip()
    status_value = request.GET.get('status', '').strip()
    search = request.GET.get('q', '').strip()
    try:
        limit = min(max(int(request.GET.get('limit', '100')), 1), 250)
    except (TypeError, ValueError):
        limit = 100

    if symbol:
        qs = qs.filter(order__symbol__iexact=symbol)
    if strategy:
        qs = qs.filter(order__strategy__iexact=strategy)
    if status_value:
        qs = qs.filter(status__iexact=status_value)
    if search:
        qs = qs.filter(
            Q(order__symbol__icontains=search)
            | Q(order__strategy__icontains=search)
            | Q(order__broker_order_id__icontains=search)
            | Q(order__client_order_id__icontains=search)
        )

    payload = []
    for report in qs.order_by('-created_at')[:limit]:
        order = report.order
        payload.append({
            'id': report.pk,
            'order_id': order.pk,
            'broker': order.broker.name,
            'account': order.account.account_id,
            'symbol': order.symbol,
            'direction': order.direction,
            'strategy': order.strategy or '—',
            'order_type': order.order_type,
            'stake': str(order.stake),
            'requested_price': str(report.requested_price) if report.requested_price is not None else None,
            'execution_price': str(report.execution_price) if report.execution_price is not None else None,
            'slippage': str(report.slippage),
            'fees': str(report.fees),
            'latency_ms': report.latency,
            'status': report.status,
            'broker_reference': order.broker_order_id or '',
            'created_at': report.created_at.isoformat(),
        })
    return JsonResponse({'status': 'success', 'count': len(payload), 'executions': payload})
