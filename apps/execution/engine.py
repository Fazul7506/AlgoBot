import asyncio, time
from types import SimpleNamespace
from django.conf import settings
from django.utils import timezone
from .services import OrderService, OrderValidationService, ExecutionQueueService, PositionService, TradeSynchronizationService
from .repositories import ExecutionLogRepository
from . import constants as c
from apps.brokers.services import BrokerRegistry
from apps.brokers.models import BrokerAccount


class ExecutionEngine:
    def _ai_market_context(self, account, symbol, timeframe='M1'):
        """Build AI context from the broker feed; never trust browser-supplied AI values."""
        from apps.market_data.models import Tick, Candle
        max_age = int(getattr(settings, 'BROKER_MARKET_DATA_MAX_AGE_SECONDS', 30))
        now = timezone.now()
        tick = Tick.objects.filter(symbol__symbol=symbol).order_by('-epoch', '-received_at').first()
        if tick is not None:
            age = max(0, (now - tick.received_at).total_seconds())
            if age <= max_age:
                candles = list(reversed(list(Candle.objects.filter(symbol__symbol=symbol, timeframe=timeframe).order_by('-epoch')[:60])))
                price = float(tick.quote)
                return {'market_data': {'close': price, 'open': price, 'high': price, 'low': price, 'bid': float(tick.bid) if tick.bid is not None else None, 'ask': float(tick.ask) if tick.ask is not None else None, 'spread': float(tick.spread or 0), 'volume': float(tick.volume or 0), 'source': 'persisted_broker_tick', 'age_seconds': round(age, 3)}, 'candles': [{'open': float(x.open), 'high': float(x.high), 'low': float(x.low), 'close': float(x.close), 'volume': float(x.volume or 0), 'epoch': x.epoch} for x in candles]}
        async def fetch(): return await asyncio.wait_for(BrokerRegistry().adapter(account.broker, account).get_market_data(symbol), timeout=7.0)
        tick_data = asyncio.run(fetch()); price = tick_data.get('price', tick_data.get('quote'))
        return {'market_data': {'close': price, 'open': price, 'high': price, 'low': price, 'bid': tick_data.get('bid'), 'ask': tick_data.get('ask'), 'spread': (tick_data.get('ask') - tick_data.get('bid')) if tick_data.get('ask') is not None and tick_data.get('bid') is not None else 0, 'source': 'live_broker_tick'}}

    @staticmethod
    def _assert_authoritative_account(user, account):
        if account is None or account.user_id != user.id:
            raise PermissionError('The selected broker account does not belong to this user')
        if not account.is_preferred:
            raise PermissionError('The selected broker account is no longer the active account')
        if not account.is_connection_eligible:
            raise PermissionError('The active broker account is not connected or its credentials are not usable')
        return account

    def place_order(self, user, **data):
        account = self._assert_authoritative_account(user, data.get('broker_account'))
        order = OrderService().create_order(user, **data); OrderValidationService().validate(order)
        from apps.risk.engine import RiskEngine
        RiskEngine().approve_or_raise(order, data.get('risk_context') or {}); ExecutionQueueService().enqueue(order, data.get('priority', 5)); return order

    def place_consensus_order(self, user, *, symbol, timeframe='M1', context=None, risk_context=None, priority=5, **data):
        """AI trade path: fresh broker context -> ensemble -> recommendation -> consensus gate -> risk -> queue."""
        from apps.ai_engine.services import PredictionService, RecommendationService, ConsensusDecisionGate
        account = self._assert_authoritative_account(user, data.get('broker_account')); context = context if context else self._ai_market_context(account, symbol, timeframe)
        prediction = PredictionService().predict(symbol, timeframe, context); recommendation = RecommendationService().recommend(symbol, prediction)
        intended = data.get('direction'); approved, reason = ConsensusDecisionGate().validate(prediction, intended)
        if not approved: raise PermissionError(reason)
        consensus = prediction.payload.get('consensus', {}) if prediction.payload else {}; direction = str(consensus.get('decision', prediction.prediction)).lower()
        if direction not in {'buy', 'sell'}: raise PermissionError('Ensemble returned a non-trade decision')
        data['direction'] = direction
        data['validation_context'] = {**(data.get('validation_context') or {}), 'ai_consensus': consensus, 'ai_prediction_id': prediction.pk, 'ai_recommendation_id': recommendation.pk, 'ai_source': 'ensemble'}
        data['risk_context'] = {**(risk_context or data.get('risk_context') or {}), 'ai_consensus_confidence': consensus.get('confidence', prediction.confidence), 'ai_consensus_decision': direction}
        order = OrderService().create_order(user, **data); OrderValidationService().validate(order)
        from apps.risk.engine import RiskEngine
        RiskEngine().approve_or_raise(order, data.get('risk_context') or {}); ExecutionQueueService().enqueue(order, priority); return order

    def cancel_order(self, order): return OrderService().cancel(order)
    def modify_order(self, order, **changes): return OrderService().modify(order, **changes)

    async def execute(self, order):
        """Final execution boundary; re-read account authority immediately before broker submission."""
        if order.status in {c.ORDER_STATUS_ACCEPTED, c.ORDER_STATUS_EXECUTED}: return order
        if order.status in {c.ORDER_STATUS_CANCELLED, c.ORDER_STATUS_FAILED}: raise PermissionError(f'Cannot execute order in {order.status} state')

        account = await asyncio.to_thread(
            BrokerAccount.objects.select_related('broker').get,
            pk=order.broker_account_id,
            user_id=order.user_id,
        )
        self._assert_authoritative_account(order.user, account)

        validation = getattr(order, 'validation_context', {}) or {}; consensus = validation.get('ai_consensus') or {}
        if validation.get('ai_source') == 'ensemble':
            decision = str(consensus.get('decision', '')).lower(); confidence = float(consensus.get('confidence', 0) or 0)
            if decision not in {'buy','sell'} or decision != str(order.direction).lower() or confidence < 65.0 or int(consensus.get('models_used', 0) or 0) < 1: raise PermissionError('Ensemble consensus validation failed at execution boundary')
        from apps.risk.engine import RiskEngine
        RiskEngine().approve_or_raise(order, validation.get('risk_context') or validation)
        start=time.perf_counter(); order.status=c.ORDER_STATUS_SENT; order.save(update_fields=['status','updated_at'])
        adapter=BrokerRegistry().adapter(account.broker, account)
        broker_order=SimpleNamespace(symbol=order.symbol,stake=order.stake,quantity=order.stake,direction=order.direction,order_type=order.order_type,price=order.price,contract_type=getattr(order,'contract_type',None),routing_context=validation)
        response=await adapter.place_order(broker_order); order.broker_response=response or {}; order.broker_reference=str((response or {}).get('broker_order_id') or (response or {}).get('contract_id') or (response or {}).get('order_id','')); order.status=c.ORDER_STATUS_EXECUTED; order.save(update_fields=['broker_response','broker_reference','status','updated_at'])
        ExecutionLogRepository().log(order,'OrderExecuted','success','Broker accepted order',(time.perf_counter()-start)*1000,response); return order

    def retry(self, order): return ExecutionQueueService().enqueue(order, queue_type='retry')
    def close_position(self, position, exit_price): return PositionService().close_position(position, exit_price)
    async def synchronize(self, broker_account): return await TradeSynchronizationService().synchronize(broker_account)
    def rollback(self, order, message='Execution rolled back'):
        order.status=c.ORDER_STATUS_FAILED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'ExecutionFailed','failed',message); return order
