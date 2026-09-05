from datetime import timedelta

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.brokers.models import BrokerAccount
from apps.execution.models import Order
from apps.notifications.models import Notification
from apps.strategies.models import StrategySignal
from core.account_context import get_active_account


class DashboardViewSet(viewsets.ViewSet):
    """Canonical dashboard API backed only by current application models."""
    permission_classes=[permissions.IsAuthenticated]

    @staticmethod
    def _limit(request,default=50,maximum=100):
        try:return min(max(int(request.query_params.get('limit',default)),1),maximum)
        except (TypeError,ValueError):return default

    @action(detail=False,methods=['get'])
    def account_overview(self,request):
        account=get_active_account(request.user,request=request)
        executed=Order.objects.filter(user=request.user,account=account) if account else Order.objects.none()
        return Response({'status':'success','data':{'account':{'id':account.id if account else None,'account_id':account.account_id if account else None,'broker':account.broker.name if account else None,'currency':account.currency if account else None,'balance':account.balance if account else None,'equity':account.equity if account else None,'last_synced_at':account.last_synced_at if account else None,'email':request.user.email,'username':request.user.username,'registered_date':request.user.date_joined.isoformat()},'trading_stats':{'total_trades':executed.count(),'open_trades':executed.count(),'wins':0,'losses':0,'win_rate':0,'total_pnl':0,'avg_pnl_per_trade':0}}},status=status.HTTP_200_OK)

    @action(detail=False,methods=['get'])
    def active_trades(self,request):
        account=get_active_account(request.user,request=request);qs=Order.objects.filter(user=request.user,account=account,status='executed') if account else Order.objects.none();rows=qs.order_by('-created_at')[:self._limit(request)]
        return Response({'status':'success','count':len(rows),'data':[{'id':row.id,'symbol':row.symbol,'stake':row.stake,'strategy':row.strategy,'created_at':row.created_at} for row in rows]})

    @action(detail=False,methods=['get'])
    def trade_history(self,request):
        try:days=max(1,int(request.query_params.get('days',30)))
        except (TypeError,ValueError):days=30
        start=timezone.now()-timedelta(days=days);account=get_active_account(request.user,request=request);qs=Order.objects.filter(user=request.user,created_at__gte=start,account=account) if account else Order.objects.none();rows=qs.order_by('-created_at')[:self._limit(request)]
        return Response({'status':'success','total':len(rows),'count':len(rows),'data':[{'id':row.id,'symbol':row.symbol,'stake':row.stake,'direction':row.direction,'status':row.status,'strategy':row.strategy,'created_at':row.created_at,'broker_reference':row.broker_reference} for row in rows]})

    @action(detail=False,methods=['get'])
    def performance_summary(self,request):
        account=get_active_account(request.user,request=request);orders=Order.objects.filter(user=request.user,account=account) if account else Order.objects.none()
        return Response({'status':'success','data':{'total_trades':orders.count(),'winning_trades':0,'losing_trades':0,'win_rate':0,'total_profit':0,'average_profit':0,'sharpe_ratio':0,'best_trade':0,'worst_trade':0}})

    @action(detail=False,methods=['get'])
    def signals(self,request):
        symbol=str(request.query_params.get('symbol') or '').strip();qs=StrategySignal.objects.select_related('strategy','configuration').order_by('-timestamp');
        if symbol:qs=qs.filter(symbol=symbol)
        rows=qs[:self._limit(request)]
        return Response({'status':'success','count':len(rows),'data':[{'id':row.id,'symbol':row.symbol,'direction':row.signal,'confidence':row.confidence,'market_regime':'','strategy':row.strategy.name,'was_executed':False,'created_at':row.timestamp} for row in rows]})

    @action(detail=False,methods=['get'])
    def notifications(self,request):
        rows=Notification.objects.filter(user=request.user).order_by('-created_at')[:self._limit(request,20)]
        return Response({'status':'success','count':len(rows),'data':[{'id':row.id,'alert_type':row.category,'message':row.message,'channels':[row.channel],'delivered_channels':[row.channel] if row.status=='sent' else [],'status':row.status,'created_at':row.created_at} for row in rows]})

    @action(detail=False,methods=['get'])
    def performance_metrics(self,request):
        account=get_active_account(request.user,request=request);orders=Order.objects.filter(user=request.user,account=account) if account else Order.objects.none()
        return Response({'status':'success','data':{'total_trades':orders.count(),'net_profit':0,'win_rate':0,'max_drawdown':0,'sharpe_ratio':0}})
