import asyncio, time
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.brokers.services import BrokerRegistry
from .exceptions import OrderValidationError, NonRetryableExecutionError
from .models import Order, ExecutionQueue, ExecutionLog
from .repositories import OrderRepository, ExecutionLogRepository, ExecutionQueueRepository
from . import constants as c

class OrderValidationService:
    def validate(self, order):
        start=time.perf_counter(); errors=[]
        if not order.symbol: errors.append('Symbol exists validation failed')
        if not order.broker_account_id or not order.broker_account.is_connected: errors.append('Broker connected validation failed')
        if order.stake <= 0: errors.append('Stake within limits validation failed')
        if order.broker_account_id and order.broker_account.balance < order.stake: errors.append('Sufficient balance validation failed')
        if order.order_type not in c.ORDER_TYPES: errors.append('Contract supported/order type validation failed')
        ExecutionLogRepository().log(order,'OrderValidated','failed' if errors else 'success','; '.join(errors), (time.perf_counter()-start)*1000)
        if errors: raise OrderValidationError('; '.join(errors))
        order.status=c.ORDER_STATUS_VALIDATED; order.save(update_fields=['status','updated_at']); return order

class OrderService:
    def create_order(self, user, **data):
        order=OrderRepository().create(user=user, **data); ExecutionLogRepository().log(order,'OrderCreated',order.status,'Order created'); return order
    def cancel(self, order): order.status=c.ORDER_STATUS_CANCELLED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'OrderCancelled','success','Order cancelled'); return order
    def modify(self, order, **changes):
        for k,v in changes.items(): setattr(order,k,v)
        order.save(); ExecutionLogRepository().log(order,'OrderModified','success','Order modified'); return order

class ExecutionQueueService:
    def enqueue(self, order, priority=5, queue_type='priority'):
        entry=ExecutionQueueRepository().enqueue(order,priority,queue_type); order.status=c.ORDER_STATUS_QUEUED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'OrderQueued','success',f'Queued in {queue_type} queue'); return entry
    def retryable(self): return ExecutionQueue.objects.filter(status__in=[c.QUEUE_STATUS_PENDING,c.QUEUE_STATUS_RETRY], next_retry__lte=timezone.now()) | ExecutionQueue.objects.filter(status=c.QUEUE_STATUS_PENDING,next_retry__isnull=True)

class PositionService:
    def open_position(self, order, entry_price):
        from apps.trading.repositories import PositionRepository
        pos=PositionRepository().open_for_order(order,entry_price); ExecutionLogRepository().log(order,'PositionOpened','success','Position opened'); return pos
    def update_position(self, position, current_price): position.current_price=current_price; position.profit_loss=(current_price-position.entry_price); position.save(update_fields=['current_price','profit_loss']); return position
    def close_position(self, position, exit_price): position.exit_price=exit_price; position.status='closed'; position.closed_at=timezone.now(); position.profit_loss=exit_price-position.entry_price; position.save(); ExecutionLogRepository().log(position.order,'PositionClosed','success','Position closed'); return position

class ContractService:
    def purchase(self, position, **data):
        from apps.contracts.repositories import ContractRepository
        contract=ContractRepository().create(position=position,**data); ExecutionLogRepository().log(position.order,'ContractPurchased','success',contract.contract_id); return contract
    def expire(self, contract, settlement=None): contract.status='expired'; contract.settlement=settlement; contract.save(update_fields=['status','settlement','updated_at']); ExecutionLogRepository().log(contract.position.order,'ContractExpired','success',contract.contract_id); return contract

class TradeLifecycleService:
    def archive(self, order): order.status=c.ORDER_STATUS_ARCHIVED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'OrderArchived','success','Trade archived'); return order

class TradeSynchronizationService:
    async def synchronize(self, broker_account):
        adapter=BrokerRegistry().adapter_for_legacy_account(broker_account)
        return {'positions': await adapter.get_positions(), 'orders': await adapter.get_orders(), 'balance': await adapter.get_balance()}

class ExecutionMonitoringService:
    def dashboard(self): return {'queue_size': ExecutionQueue.objects.exclude(status__in=[c.QUEUE_STATUS_DONE,c.QUEUE_STATUS_CANCELLED]).count(), 'pending_orders': Order.objects.filter(status__in=[c.ORDER_STATUS_DRAFT,c.ORDER_STATUS_VALIDATED,c.ORDER_STATUS_QUEUED]).count(), 'average_latency': 0}

class ExecutionAnalyticsService:
    def summary(self): return {'orders': Order.objects.count(), 'executed': Order.objects.filter(status=c.ORDER_STATUS_EXECUTED).count(), 'failed': Order.objects.filter(status=c.ORDER_STATUS_FAILED).count()}
