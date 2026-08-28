from collections import Counter
from decimal import Decimal

from django.db.models import Avg, Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import MarketSymbol, MarketSnapshot
from trading.models.core import Signal


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def market_intelligence(request):
    """Backend-driven market intelligence with explicit evidence/confluence."""
    symbol_filter = str(request.query_params.get('symbol') or '').strip()
    limit = max(1, min(int(request.query_params.get('limit', 50) or 50), 100))
    symbols = MarketSymbol.objects.filter(is_active=True, is_tradable=True).select_related('snapshot')
    if symbol_filter:
        symbols = symbols.filter(symbol=symbol_filter)

    signals = Signal.objects.filter(symbol__in=symbols.values_list('symbol', flat=True)).order_by('-created_at')
    latest_by_symbol = {}
    for signal in signals:
        latest_by_symbol.setdefault(signal.symbol, []).append(signal)

    results=[]
    for market in symbols[:limit]:
        snapshot=getattr(market, 'snapshot', None)
        evidence=[]
        score=Decimal('0')
        if snapshot is not None:
            change=Decimal(str(snapshot.change_percent or 0))
            spread=Decimal(str(snapshot.spread or 0))
            if change > 0: score += 1; evidence.append('positive_price_change')
            elif change < 0: score -= 1; evidence.append('negative_price_change')
            if spread >= 0: evidence.append('broker_spread_observed')
        recent=latest_by_symbol.get(market.symbol, [])[:12]
        directions=Counter(s.direction for s in recent if s.direction in {'BUY','SELL'})
        if directions:
            dominant,count=directions.most_common(1)[0]
            opposing=directions.get('SELL' if dominant == 'BUY' else 'BUY', 0)
            if count > opposing: score += Decimal('1') if dominant == 'BUY' else Decimal('-1')
            evidence.append(f'signal_confluence_{dominant.lower()}')
        results.append({
            'symbol':market.symbol,'display_name':market.display_name,'market':market.market,'sub_market':market.sub_market,
            'status':'ready' if snapshot is not None else 'no_data','confluence_score':float(score),
            'signal_count':len(recent),'buy_signals':directions.get('BUY',0),'sell_signals':directions.get('SELL',0),
            'evidence':evidence,
            'snapshot_timestamp':snapshot.timestamp.isoformat() if snapshot else None,
            'source':'broker_snapshot_store_and_strategy_signals'
        })
    results.sort(key=lambda row: row['confluence_score'], reverse=True)
    return Response({'status':'ok','source':'backend_market_intelligence','count':len(results),'results':results})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def signal_lifecycle(request):
    """Expose signal lifecycle state derived from persisted signals and executions."""
    symbol=str(request.query_params.get('symbol') or '').strip()
    qs=Signal.objects.all().order_by('-created_at')
    if symbol: qs=qs.filter(symbol=symbol)
    rows=list(qs[:100])
    data=[]
    for signal in rows:
        age_seconds=max(0, int((__import__('django').utils.timezone.now()-signal.created_at).total_seconds()))
        if signal.was_executed: lifecycle='executed'
        elif age_seconds <= 300: lifecycle='active'
        else: lifecycle='expired'
        data.append({'id':signal.id,'symbol':signal.symbol,'direction':signal.direction,'confidence':signal.confidence,'strategy':signal.strategy,'timeframe':signal.timeframe,'market_regime':signal.market_regime,'created_at':signal.created_at.isoformat(),'age_seconds':age_seconds,'lifecycle':lifecycle,'was_executed':signal.was_executed})
    return Response({'status':'ok','source':'persisted_strategy_signals','count':len(data),'signals':data})
