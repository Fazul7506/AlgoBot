from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from django.conf import settings
from django.utils import timezone
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
    def _environment(account): return str((account.credentials or {}).get('account_type') or '').lower().strip() if account else ''
    @staticmethod
    def _safe_client_context(data):
        context = data.get('validation_context') or {}
        return {'broker_source': context.get('broker_source') or 'connected_broker', 'contract_type': context.get('contract_type'), 'underlying_symbol': context.get('underlying_symbol') or data.get('symbol'), 'selected_strategy': context.get('selected_strategy') or data.get('strategy') or None}
    def create(self, request, *args, **kwargs):
        client_request_id = str(request.data.get('client_request_id') or '').strip()
        if client_request_id:
            existing = Order.objects.filter(user=request.user, client_request_id=client_request_id).first()
            if existing: return response.Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data); account = data.get('broker_account'); environment = self._environment(account); data['validation_context'] = self._safe_client_context(request.data)
        if environment == 'real':
            allowed, used, limit = check_live_order(request.user)
            if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            if not bool(getattr(settings, 'ALLOW_LIVE_TRADING', False)): return response.Response({'status':'rejected','code':'LIVE_TRADING_DISABLED','detail':'Live-money trading is disabled by platform configuration.'}, status=status.HTTP_409_CONFLICT)
            try: order = ExecutionEngine().place_consensus_order(request.user, timeframe='M1', context=None, risk_context={}, **data)
            except PermissionError as exc: return response.Response({'status':'rejected','code':'AI_CONSENSUS_GATE_REJECTED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
            except Exception as exc: return response.Response({'status':'rejected','code':'AI_ANALYSIS_UNAVAILABLE','detail':f'Live execution requires a fresh verified AI decision: {exc}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return response.Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)
        try: order = ExecutionEngine().place_order(request.user, **data)
        except PermissionError as exc: return response.Response({'status':'rejected','code':'ORDER_RISK_GATE_REJECTED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
        return response.Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)
    @decorators.action(detail=False, methods=['post'])
    def preview(self, request):
        serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data; account = data.get('broker_account')
        if account is None or account.user_id != request.user.id: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_REQUIRED','detail':'Select a connected broker account.'}, status=status.HTTP_409_CONFLICT)
        if not account.is_connection_eligible: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_NOT_READY','detail':'The selected broker account is not connected or its credentials are not usable.'}, status=status.HTTP_409_CONFLICT)
        environment = self._environment(account)
        if not environment: return response.Response({'status':'rejected','code':'ACCOUNT_ENVIRONMENT_UNVERIFIED','detail':'Broker account environment has not been verified.'}, status=status.HTTP_409_CONFLICT)
        if environment == 'real' and not bool(getattr(account.broker, 'supports_live', False)): return response.Response({'status':'rejected','code':'LIVE_BROKER_UNSUPPORTED','detail':'The selected broker is not live-trading capable.'}, status=status.HTTP_409_CONFLICT)
        if environment == 'real':
            allowed, used, limit = check_live_order(request.user)
            if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            if not bool(getattr(settings, 'ALLOW_LIVE_TRADING', False)): return response.Response({'status':'rejected','code':'LIVE_TRADING_DISABLED','detail':'Live-money trading is disabled by platform configuration.'}, status=status.HTTP_409_CONFLICT)
        try:
            from apps.brokers.services import MarketDataFreshnessService
            try:
                quote = MarketDataFreshnessService().latest(data.get('symbol'))
            except Exception:
                # The terminal also consumes fresh persisted Tick records. Treat
                # a fresh tick as an authoritative preview quote when the
                # snapshot writer is briefly behind; never use browser data.
                from apps.market_data.models import Tick
                tick = Tick.objects.filter(symbol__symbol=data.get('symbol')).order_by('-epoch', '-received_at').first()
                if tick is None: raise
                age = max(0, (timezone.now() - tick.received_at).total_seconds())
                max_age = int(getattr(settings, 'BROKER_MARKET_DATA_MAX_AGE_SECONDS', 30))
                if age > max_age: raise
                quote = SimpleNamespace(last_price=tick.quote, bid=tick.bid, ask=tick.ask, spread=tick.spread, timestamp=tick.received_at)
        except Exception as exc:
            return response.Response({'status':'rejected','code':'MARKET_DATA_GATE_FAILED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
        ai_gate = {'ai_verified':False,'ai_required':environment == 'real'}
        if environment == 'real':
            try:
                from apps.ai_engine.services import PredictionService, RecommendationService, ConsensusDecisionGate
                context = ExecutionEngine()._ai_market_context(account, data.get('symbol'), 'M1')
                prediction = PredictionService().predict(data.get('symbol'), 'M1', context)
                recommendation = RecommendationService().recommend(data.get('symbol'), prediction)
                approved, reason = ConsensusDecisionGate().validate(prediction, data.get('direction'))
                if not approved: return response.Response({'status':'rejected','code':'AI_CONSENSUS_GATE_REJECTED','detail':reason}, status=status.HTTP_409_CONFLICT)
                consensus = prediction.payload.get('consensus', {}) if prediction.payload else {}
                ai_gate = {'ai_verified':True,'ai_required':True,'prediction_id':prediction.pk,'recommendation_id':recommendation.pk,'decision':consensus.get('decision',prediction.prediction),'confidence':consensus.get('confidence',prediction.confidence),'models_used':consensus.get('models_used',0)}
            except Exception as exc: return response.Response({'status':'rejected','code':'AI_ANALYSIS_UNAVAILABLE','detail':f'Live execution requires a fresh verified AI decision: {exc}'}, status=status.HTTP_409_CONFLICT)
        try:
            stake = data.get('stake')
            try: stake_value = float(Decimal(str(stake)))
            except (InvalidOperation, TypeError, ValueError): stake_value = None
            last_price = getattr(quote, 'last_price', None)
            if last_price is None: raise ValueError('The authoritative market snapshot has no last price.')
            timestamp = getattr(quote, 'timestamp', None)
            market = {'price':float(last_price),'bid':float(quote.bid) if quote.bid is not None else None,'ask':float(quote.ask) if quote.ask is not None else None,'spread':float(quote.spread or 0),'timestamp':timestamp.isoformat() if timestamp else None}
            return response.Response({'status':'ready','source':'authoritative_pre_trade_preview','account':{'id':account.id,'broker':account.broker.name,'account_id':account.account_id,'environment':environment,'supports_live':bool(getattr(account.broker,'supports_live',False))},'order':{'symbol':data.get('symbol'),'direction':data.get('direction'),'order_type':data.get('order_type'),'stake':stake_value,'strategy':data.get('strategy','')},'market':market,'gates':{'account_connected':True,'environment_verified':True,'plan_live_trading':True,'live_trading_allowed':environment != 'real' or bool(getattr(settings,'ALLOW_LIVE_TRADING',False)),'live_order_limit':True,'fresh_market_data':True,**ai_gate}})
        except (TypeError, ValueError, AttributeError, OverflowError) as exc:
            return response.Response({'status':'rejected','code':'PREVIEW_SERIALIZATION_FAILED','detail':f'Unable to build a safe pre-trade preview: {exc}'}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            return response.Response({'status':'rejected','code':'PREVIEW_FAILED','detail':'Unable to complete the pre-trade preview safely.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None): return response.Response(OrderSerializer(ExecutionEngine().cancel_order(self.get_object())).data)
    @decorators.action(detail=True, methods=['post'])
    def retry(self, request, pk=None): ExecutionEngine().retry(self.get_object()); return response.Response({'status':'queued'})


class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PositionSerializer; permission_classes=[permissions.IsAuthenticated]
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
        if status_value in {ReconciliationEvent.STATUS_OPEN,ReconciliationEvent.STATUS_REVIEWED}: qs=qs.filter(status=status_value)
        if broker_account and broker_account.isdigit(): qs=qs.filter(broker_account_id=int(broker_account))
        return qs
    @decorators.action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        event=self.get_object()
        if event.status == ReconciliationEvent.STATUS_REVIEWED: return response.Response(self.get_serializer(event).data)
        event.mark_reviewed(request.user); return response.Response(self.get_serializer(event).data)
