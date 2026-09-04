import asyncio, time
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone
from asgiref.sync import sync_to_async
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

class TradeReconciliationService:
    """Compare local execution state with broker-authoritative state without mutating either side."""

    @staticmethod
    def _broker_reference(record):
        if not isinstance(record, dict):
            return ''
        for key in ('contract_id', 'broker_order_id', 'order_id', 'transaction_id', 'id'):
            value = record.get(key)
            if value not in (None, ''):
                return str(value)
        return ''

    @staticmethod
    def _broker_symbol(record):
        if not isinstance(record, dict):
            return ''
        return str(record.get('symbol') or record.get('underlying_symbol') or '')

    @staticmethod
    def _money(value):
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _record_discrepancy(order_id, report):
        order = Order.objects.get(pk=order_id)
        ExecutionLogRepository().log(
            order,
            'ReconciliationDiscrepancy',
            'warning',
            'Broker and local execution state differ; no automatic mutation was performed',
            None,
            report,
        )

    async def compare(self, broker_account, broker_positions, broker_orders, broker_balance):
        local_orders = await sync_to_async(list)(
            Order.objects.filter(broker_account=broker_account).only(
                'id', 'symbol', 'status', 'broker_reference', 'client_request_id', 'created_at'
            )
        )

        broker_by_ref = {}
        for source, records in (('order', broker_orders or []), ('position', broker_positions or [])):
            for record in records:
                if not isinstance(record, dict):
                    continue
                reference = self._broker_reference(record)
                if reference:
                    broker_by_ref.setdefault(reference, {'record': record, 'source': source})

        matched = []
        local_missing = []
        broker_only = []
        symbol_mismatch = []
        seen_local_refs = set()

        for order in local_orders:
            reference = str(order.broker_reference or '')
            if not reference:
                if order.status in {c.ORDER_STATUS_SENT, c.ORDER_STATUS_ACCEPTED, c.ORDER_STATUS_EXECUTED}:
                    local_missing.append({
                        'order_id': order.id,
                        'symbol': order.symbol,
                        'status': order.status,
                        'reason': 'Local order has no broker reference',
                    })
                continue

            seen_local_refs.add(reference)
            broker_item = broker_by_ref.get(reference)
            if broker_item is None:
                local_missing.append({
                    'order_id': order.id,
                    'symbol': order.symbol,
                    'broker_reference': reference,
                    'status': order.status,
                    'reason': 'Local broker reference was not found in broker state',
                })
                continue

            broker_record = broker_item['record']
            broker_symbol = self._broker_symbol(broker_record)
            if broker_symbol and broker_symbol != str(order.symbol):
                symbol_mismatch.append({
                    'order_id': order.id,
                    'broker_reference': reference,
                    'local_symbol': order.symbol,
                    'broker_symbol': broker_symbol,
                })
                continue

            matched.append({
                'order_id': order.id,
                'broker_reference': reference,
                'symbol': order.symbol,
                'local_status': order.status,
                'broker_source': broker_item['source'],
            })

        for reference, broker_item in broker_by_ref.items():
            if reference not in seen_local_refs:
                broker_only.append({
                    'broker_reference': reference,
                    'symbol': self._broker_symbol(broker_item['record']),
                    'source': broker_item['source'],
                })

        local_balance = self._money(getattr(broker_account, 'balance', None))
        broker_balance_value = self._money((broker_balance or {}).get('balance')) if isinstance(broker_balance, dict) else self._money(broker_balance)
        balance_mismatch = None
        if local_balance is not None and broker_balance_value is not None and local_balance != broker_balance_value:
            balance_mismatch = {
                'local': str(local_balance),
                'broker': str(broker_balance_value),
                'delta': str(broker_balance_value - local_balance),
            }

        status = 'matched'
        if local_missing or broker_only or symbol_mismatch or balance_mismatch:
            status = 'discrepancy'

        report = {
            'status': status,
            'checked_at': timezone.now().isoformat(),
            'matched': matched,
            'local_missing': local_missing,
            'broker_only': broker_only,
            'symbol_mismatch': symbol_mismatch,
            'balance_mismatch': balance_mismatch,
            'counts': {
                'matched': len(matched),
                'local_missing': len(local_missing),
                'broker_only': len(broker_only),
                'symbol_mismatch': len(symbol_mismatch),
            },
        }

        discrepancy_orders = {item.get('order_id') for item in local_missing + symbol_mismatch if item.get('order_id')}
        if discrepancy_orders:
            await sync_to_async(self._record_discrepancy)(discrepancy_orders.pop(), report)
            for order_id in discrepancy_orders:
                await sync_to_async(self._record_discrepancy)(order_id, report)

        return report

class TradeSynchronizationService:
    async def synchronize(self, broker_account):
        adapter=BrokerRegistry().adapter_for_legacy_account(broker_account)
        positions = await adapter.get_positions()
        orders = await adapter.get_orders()
        balance = await adapter.get_balance()
        reconciliation = await TradeReconciliationService().compare(broker_account, positions, orders, balance)
        return {'positions': positions, 'orders': orders, 'balance': balance, 'reconciliation': reconciliation}

class ExecutionMonitoringService:
    def dashboard(self):
        queue_size = ExecutionQueue.objects.exclude(
            status__in=[c.QUEUE_STATUS_DONE, c.QUEUE_STATUS_CANCELLED]
        ).count()
        pending_orders = Order.objects.filter(
            status__in=[c.ORDER_STATUS_DRAFT, c.ORDER_STATUS_VALIDATED, c.ORDER_STATUS_QUEUED]
        ).count()
        average_latency = ExecutionLog.objects.filter(
            latency__isnull=False
        ).aggregate(value=Avg('latency'))['value'] or 0
        return {
            'queue_size': queue_size,
            'pending_orders': pending_orders,
            'average_latency': float(average_latency),
        }

class ExecutionAnalyticsService:
    def summary(self): return {'orders': Order.objects.count(), 'executed': Order.objects.filter(status=c.ORDER_STATUS_EXECUTED).count(), 'failed': Order.objects.filter(status=c.ORDER_STATUS_FAILED).count()}
