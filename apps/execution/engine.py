import asyncio, time
from types import SimpleNamespace
from .services import OrderService, OrderValidationService, ExecutionQueueService, PositionService, TradeSynchronizationService
from .repositories import ExecutionLogRepository
from . import constants as c
from apps.brokers.services import BrokerRegistry


class ExecutionEngine:
    def place_order(self, user, **data):
        """Legacy/manual order path. Existing callers remain compatible."""
        order=OrderService().create_order(user, **data); OrderValidationService().validate(order)
        from apps.risk.engine import RiskEngine
        RiskEngine().approve_or_raise(order, data.get('risk_context') or {}); ExecutionQueueService().enqueue(order, data.get('priority',5)); return order

    def place_consensus_order(self, user, *, symbol, timeframe='M1', context=None, risk_context=None, priority=5, **data):
        """AI trade path: ensemble -> recommendation -> consensus gate -> risk -> queue."""
        from apps.ai_engine.services import PredictionService, RecommendationService, ConsensusDecisionGate
        prediction=PredictionService().predict(symbol, timeframe, context or {})
        recommendation=RecommendationService().recommend(symbol, prediction)
        intended=data.get('direction')
        approved, reason=ConsensusDecisionGate().validate(prediction, intended)
        if not approved:
            raise PermissionError(reason)
        consensus=prediction.payload.get('consensus',{}) if prediction.payload else {}
        direction=consensus.get('decision', prediction.prediction)
        if direction not in {'BUY','SELL'}:
            raise PermissionError('Ensemble returned a non-trade decision')
        data['direction']=direction
        data['validation_context']={**(data.get('validation_context') or {}),'ai_consensus':consensus,'ai_prediction_id':prediction.pk,'ai_recommendation_id':recommendation.pk,'ai_source':'ensemble'}
        data['risk_context']={**(risk_context or data.get('risk_context') or {}),'ai_consensus_confidence':consensus.get('confidence',prediction.confidence),'ai_consensus_decision':direction}
        order=OrderService().create_order(user, **data); OrderValidationService().validate(order)
        from apps.risk.engine import RiskEngine
        RiskEngine().approve_or_raise(order, data.get('risk_context') or {}); ExecutionQueueService().enqueue(order, priority); return order

    def cancel_order(self, order): return OrderService().cancel(order)
    def modify_order(self, order, **changes): return OrderService().modify(order, **changes)

    async def execute(self, order):
        """Final execution boundary; never sends an ensemble order that has lost its consensus metadata."""
        validation=getattr(order,'validation_context',{}) or {}; consensus=validation.get('ai_consensus') or {}
        if validation.get('ai_source') == 'ensemble':
            decision=str(consensus.get('decision','')).upper(); confidence=float(consensus.get('confidence',0) or 0)
            if decision not in {'BUY','SELL'} or decision != str(order.direction).upper() or confidence < 65.0 or int(consensus.get('models_used',0) or 0) < 1:
                raise PermissionError('Ensemble consensus validation failed at execution boundary')
        start=time.perf_counter(); order.status=c.ORDER_STATUS_SENT; order.save(update_fields=['status','updated_at'])
        adapter = BrokerRegistry().adapter_for_legacy_account(order.broker_account)
        broker_order = SimpleNamespace(symbol=order.symbol,stake=order.stake,quantity=order.stake,direction=order.direction,order_type=order.order_type,price=order.price,contract_type=getattr(order,'contract_type',None),routing_context=validation)
        response=await adapter.place_order(broker_order)
        order.broker_response=response or {}; order.broker_reference=str((response or {}).get('broker_order_id') or (response or {}).get('contract_id') or (response or {}).get('order_id','')); order.status=c.ORDER_STATUS_EXECUTED; order.save(update_fields=['broker_response','broker_reference','status','updated_at'])
        ExecutionLogRepository().log(order,'OrderExecuted','success','Broker accepted order',(time.perf_counter()-start)*1000,response); return order

    def retry(self, order): return ExecutionQueueService().enqueue(order, queue_type='retry')
    def close_position(self, position, exit_price): return PositionService().close_position(position, exit_price)
    async def synchronize(self, broker_account): return await TradeSynchronizationService().synchronize(broker_account)
    def rollback(self, order, message='Execution rolled back'):
        order.status=c.ORDER_STATUS_FAILED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'ExecutionFailed','failed',message); return order
