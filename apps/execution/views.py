from decimal import Decimal, InvalidOperation
from rest_framework import viewsets, permissions, decorators, response, status
from .models import Order, ExecutionLog, ReconciliationEvent
from apps.trading.models import Position
from apps.contracts.models import Contract
from .serializers import OrderSerializer, PositionSerializer, ContractSerializer, ExecutionLogSerializer, ReconciliationEventSerializer
from .engine import ExecutionEngine
from core.billing_entitlements import check_live_order, effective_plan


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Order.objects.filter(user=self.request.user)
    @staticmethod
    def _ai_context(data): return data.get('validation_context') or {}
    @classmethod
    def _require_ai_context(cls, data):
        context=cls._ai_context(data); prediction=str(context.get('ai_prediction') or '').upper(); recommendation=str(context.get('ai_recommendation') or '').upper(); confidence=context.get('ai_confidence'); actionable=context.get('ai_actionable')
        if not prediction and not recommendation: return False, {'status':'rejected','code':'AI_ANALYSIS_REQUIRED','detail':'Run AI analysis for the selected broker market before placing an order.'}
        if prediction not in {'BUY','SELL','AVOID'} and recommendation not in {'BUY','SELL','AVOID','WAIT'}: return False, {'status':'rejected','code':'AI_DECISION_INVALID','detail':'The AI decision is not a supported BUY, SELL or AVOID decision.'}
        if recommendation in {'AVOID','WAIT'} or prediction == 'AVOID' or actionable is False: return False, {'status':'rejected','code':'AI_DECISION_NOT_ACTIONABLE','detail':'AI analysis did not approve this market for trading.'}
        try:
            if confidence is not None and float(confidence if float(confidence) <= 1 else float(confidence) / 100) < .65: return False, {'status':'rejected','code':'AI_CONFIDENCE_TOO_LOW','detail':'AI confidence is below the 65% execution gate.'}
        except (TypeError, ValueError): return False, {'status':'rejected','code':'AI_CONFIDENCE_INVALID','detail':'AI confidence is invalid. Run AI analysis again.'}
        return True, None
    def create(self, request, *args, **kwargs):
        client_request_id=str(request.data.get('client_request_id') or '').strip()
        if client_request_id:
            existing=Order.objects.filter(user=request.user, client_request_id=client_request_id).first()
            if existing: return response.Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); data=serializer.validated_data; account=data.get('broker_account'); environment=str((account.credentials or {}).get('account_type') or '').lower().strip() if account else ''
        if environment == 'real':
            allowed, used, limit=check_live_order(request.user)
            if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        ai_ok, ai_error=self._require_ai_context(data)
        if not ai_ok: return response.Response(ai_error, status=status.HTTP_409_CONFLICT)
        try:
            order_data=dict(data); order_data.pop('risk_context',None); order_data.pop('ai_context',None); order_data.pop('timeframe',None)
            order=ExecutionEngine().place_consensus_order(request.user, symbol=order_data.pop('symbol'), timeframe=str(self._ai_context(data).get('timeframe') or 'M1').upper(), context=data.get('ai_context') or {}, risk_context=data.get('risk_context') or {}, **order_data)
        except PermissionError as exc: return response.Response({'status':'rejected','code':'ORDER_RISK_GATE_REJECTED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
        return response.Response(self.get_serializer(order).data, status=201)
    @decorators.action(detail=False, methods=['post'])
    def preview(self, request):
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); data=serializer.validated_data; account=data.get('broker_account')
        if account is None or account.user_id != request.user.id: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_REQUIRED','detail':'Select a connected broker account.'}, status=status.HTTP_409_CONFLICT)
        if not account.is_connection_eligible: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_NOT_READY','detail':'The selected broker account is not connected or its credentials are not usable.'}, status=status.HTTP_409_CONFLICT)
        environment=str((account.credentials or {}).get('account_type') or '').lower().strip()
        if not environment: return response.Response({'status':'rejected','code':'ACCOUNT_ENVIRONMENT_UNVERIFIED','detail':'Broker account environment has not been verified.'}, status=status.HTTP_409_CONFLICT)
        if environment == 'real' and not bool(getattr(account.broker, 'supports_live', False)): return response.Response({'status':'rejected','code':'LIVE_BROKER_UNSUPPORTED','detail':'The selected broker is not live-trading capable.'}, status=status.HTTP_409_CONFLICT)
        if environment == 'real':
            allowed, used, limit=check_live_order(request.user)
            if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            from django.conf import settings
            if not bool(getattr(settings, 'ALLOW_LIVE_TRADING', False)): return response.Response({'status':'rejected','code':'LIVE_TRADING_DISABLED','detail':'Live-money trading is disabled by platform configuration.'}, status=status.HTTP_409_CONFLICT)
        ai_ok, ai_error=self._require_ai_context(data)
        if not ai_ok: return response.Response({**ai_error,'ai_gate':{'required':True,'approved':False,'reason':ai_error['detail']}}, status=status.HTTP_409_CONFLICT)
        try:
            from apps.brokers.services import MarketDataFreshnessService
            quote=MarketDataFreshnessService().latest(data.get('symbol'))
        except Exception as exc: return response.Response({'status':'rejected','code':'MARKET_DATA_GATE_FAILED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
        ai_gate={'required':True,'approved':False,'reason':'AI consensus has not yet been revalidated.'}
        try:
            from apps.ai_engine.services import PredictionService, ConsensusDecisionGate
            timeframe=str(self._ai_context(data).get('timeframe') or 'M1').upper(); prediction=PredictionService().predict(data.get('symbol'),timeframe,data.get('ai_context') or {}); approved,reason=ConsensusDecisionGate().validate(prediction,data.get('direction')); consensus=(prediction.payload or {}).get('consensus') or {}
            ai_gate={'required':True,'approved':approved,'reason':reason,'decision':consensus.get('decision',prediction.prediction),'confidence':consensus.get('confidence',prediction.confidence),'models_used':consensus.get('models_used',0)}
            if not approved: return response.Response({'status':'rejected','code':'AI_CONSENSUS_REJECTED','detail':reason,'ai_gate':ai_gate}, status=status.HTTP_409_CONFLICT)
        except PermissionError as exc: return response.Response({'status':'rejected','code':'AI_CONSENSUS_REJECTED','detail':str(exc),'ai_gate':{**ai_gate,'reason':str(exc)}}, status=status.HTTP_409_CONFLICT)
        except Exception as exc: return response.Response({'status':'rejected','code':'AI_GATE_FAILED','detail':f'AI pre-trade validation failed: {exc}','ai_gate':{**ai_gate,'reason':str(exc)}}, status=status.HTTP_409_CONFLICT)
        stake=data.get('stake')
        try: stake_value=float(Decimal(str(stake)))
        except (InvalidOperation, TypeError, ValueError): stake_value=None
        return response.Response({'status':'ready','source':'authoritative_pre_trade_preview','account':{'id':account.id,'broker':account.broker.name,'account_id':account.account_id,'environment':environment,'supports_live':bool(getattr(account.broker,'supports_live',False))},'order':{'symbol':data.get('symbol'),'direction':data.get('direction'),'order_type':data.get('order_type'),'stake':stake_value,'strategy':data.get('strategy','')},'market':{'price':float(quote.last_price),'bid':float(quote.bid) if quote.bid is not None else None,'ask':float(quote.ask) if quote.ask is not None else None,'spread':float(quote.spread or 0),'timestamp':quote.timestamp.isoformat()},'gates':{'account_connected':True,'environment_verified':True,'plan_live_trading':True,'live_trading_allowed':environment != 'real' or bool(getattr(__import__('django.conf',fromlist=['settings']).settings,'ALLOW_LIVE_TRADING',False)),'live_order_limit':True,'fresh_market_data':True},'ai_gate':ai_gate})
    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None): return response.Response(OrderSerializer(ExecutionEngine().cancel_order(self.get_object())).data)
    @decorators.action(detail=True, methods=['post'])
    def retry(self, request, pk=None): ExecutionEngine().retry(self.get_object()); return response.Response({'status':'queued'})

class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PositionSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Position.objects.filter(order__user=self.request.user)
    @decorators.action(detail=False)
    def open(self, request): return response.Response(self.get_serializer(self.get_queryset().filter(status='open'),many=True).data)
    @decorators.action(detail=False)
    def closed(self, request): return response.Response(self.get_serializer(self.get_queryset().filter(status='closed'),many=True).data)
class ContractViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ContractSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Contract.objects.filter(position__order__user=self.request.user)
class ExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ExecutionLogSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return ExecutionLog.objects.filter(order__user=self.request.user)
class ReconciliationEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ReconciliationEventSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self):
        qs=ReconciliationEvent.objects.filter(user=self.request.user).select_related('broker_account','reviewed_by'); status_value=self.request.query_params.get('status'); broker_account=self.request.query_params.get('broker_account')
        if status_value in {ReconciliationEvent.STATUS_OPEN, ReconciliationEvent.STATUS_REVIEWED}: qs=qs.filter(status=status_value)
        if broker_account and broker_account.isdigit(): qs=qs.filter(broker_account_id=int(broker_account))
        return qs
    @decorators.action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        event=self.get_object()
        if event.status == ReconciliationEvent.STATUS_REVIEWED: return response.Response(self.get_serializer(event).data)
        event.mark_reviewed(request.user); return response.Response(self.get_serializer(event).data)
