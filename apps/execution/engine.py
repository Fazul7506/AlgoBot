import asyncio, time
from .services import OrderService, OrderValidationService, ExecutionQueueService, PositionService, TradeSynchronizationService
from .repositories import ExecutionLogRepository
from . import constants as c
from apps.broker.services import BrokerService
class ExecutionEngine:
    def place_order(self, user, **data):
        order=OrderService().create_order(user, **data); OrderValidationService().validate(order); ExecutionQueueService().enqueue(order, data.get('priority',5)); return order
    def cancel_order(self, order): return OrderService().cancel(order)
    def modify_order(self, order, **changes): return OrderService().modify(order, **changes)
    async def execute(self, order):
        start=time.perf_counter(); order.status=c.ORDER_STATUS_SENT; order.save(update_fields=['status','updated_at'])
        response=await BrokerService().buy(order.broker_account, symbol=order.symbol, stake=str(order.stake), direction=order.direction, order_type=order.order_type, price=str(order.price or ''))
        order.broker_response=response or {}; order.broker_reference=str((response or {}).get('contract_id') or (response or {}).get('order_id','')); order.status=c.ORDER_STATUS_EXECUTED; order.save(update_fields=['broker_response','broker_reference','status','updated_at'])
        ExecutionLogRepository().log(order,'OrderExecuted','success','Broker accepted order',(time.perf_counter()-start)*1000,response); return order
    def retry(self, order): return ExecutionQueueService().enqueue(order, queue_type='retry')
    def close_position(self, position, exit_price): return PositionService().close_position(position, exit_price)
    async def synchronize(self, broker_account): return await TradeSynchronizationService().synchronize(broker_account)
    def rollback(self, order, message='Execution rolled back'):
        order.status=c.ORDER_STATUS_FAILED; order.save(update_fields=['status','updated_at']); ExecutionLogRepository().log(order,'ExecutionFailed','failed',message); return order
