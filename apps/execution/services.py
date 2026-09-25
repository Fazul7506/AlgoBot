import asyncio, time
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone
from asgiref.sync import sync_to_async
from apps.brokers.services import BrokerRegistry
from apps.brokers.position_sync import BrokerPositionSyncService
from .exceptions import OrderValidationError, NonRetryableExecutionError
from .models import Order, ExecutionQueue, ExecutionLog
from .repositories import OrderRepository, ExecutionLogRepository, ExecutionQueueRepository
from . import constants as c


def _broker_datetime(value):
    if value in (None, ''):
        return None
    try:
        from datetime import datetime, timezone as dt_timezone
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

class OrderValidationService:
    def validate(self, order):
        start=time.perf_counter(); errors=[]
        if not order.symbol: errors.append('Symbol exists validation failed')
        if not order.broker_account_id or not order.broker_account.is_connected: errors.append('Broker connected validation failed')
        if order.stake <= 0: errors.append('Stake within limits validation failed')
        broker_type = str(getattr(getattr(order.broker_account, 'broker', None), 'broker_type', '') or '').lower()
        if broker_type == 'deriv' and not str(getattr(order, 'contract_type', '') or '').strip():
            errors.append('Broker contract type is required for Deriv execution')
        duration = getattr(order, 'duration', None)
        duration_unit = str(getattr(order, 'duration_unit', '') or '').strip().lower()
        if duration is not None and not duration_unit:
            errors.append('Duration unit is required when a duration is supplied')
        if duration_unit and duration is None:
            errors.append('Duration is required when a duration unit is supplied')
        if duration is not None and duration <= 0:
            errors.append('Duration must be positive')
        routing = getattr(order, 'validation_context', {}) or {}
        requested_currency = str(routing.get('currency') or '').upper()
        account_currency = str(getattr(order.broker_account, 'currency', '') or '').upper()
        if requested_currency and account_currency and requested_currency != account_currency:
            errors.append('Order currency does not match the authoritative broker account currency')
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
    """Compatibility facade over the canonical broker-owned Position model."""

    def open_position(self, order, entry_price=None, broker_contract=None):
        from apps.brokers.models import Position

        contract = dict(broker_contract or {})
        contract_id = contract.get("contract_id") or getattr(order, "broker_reference", None)
        if not contract_id:
            raise ValueError("A broker contract ID is required before a position can be created.")
        if not contract:
            raise ValueError("A broker contract response is required before a position can be created.")

        position, _ = Position.objects.update_or_create(
            account=order.broker_account,
            contract_id=str(contract_id),
            defaults={
                "broker": order.broker_account.broker,
                "transaction_id": str(contract.get("transaction_id") or ""),
                "broker_order_id": str(contract.get("order_id") or order.broker_reference or ""),
                "symbol": str(contract.get("underlying_symbol") or order.symbol or ""),
                "contract_type": str(contract.get("contract_type") or order.contract_type or ""),
                "direction": str(contract.get("direction") or ""),
                "stake": contract.get("buy_price"),
                "size": contract.get("amount") or contract.get("quantity"),
                "entry_price": contract.get("buy_price"),
                "current_price": contract.get("bid_price") if contract.get("bid_price") is not None else contract.get("current_spot"),
                "payout": contract.get("payout"),
                "profit": contract.get("profit"),
                "currency": str(contract.get("currency") or order.broker_account.currency or ""),
                "status": str(contract.get("status") or ("closed" if contract.get("is_sold") else "open")),
                "opened_at": _broker_datetime(contract.get("date_start") or contract.get("purchase_time")),
                "expiry_time": _broker_datetime(contract.get("date_expiry")),
                "closed_at": _broker_datetime(contract.get("sell_spot_time") or contract.get("exit_spot_time")),
                "raw_data": contract,
                "last_synced_at": timezone.now(),
            },
        )
        ExecutionLogRepository().log(order, "PositionOpened", "success", "Broker-authoritative position synchronized")
        return position

    def update_position(self, position, broker_contract=None):
        contract = dict(broker_contract or {})
        if not contract or str(contract.get("contract_id") or "") != str(position.contract_id):
            raise ValueError("A matching broker contract is required to update a position.")
        current_price = contract.get("bid_price")
        if current_price is None:
            current_price = contract.get("current_spot")
        if current_price is None:
            return position
        position.current_price = current_price
        position.profit = contract.get("profit")
        position.payout = contract.get("payout")
        position.status = str(contract.get("status") or ("closed" if contract.get("is_sold") else position.status))
        position.last_synced_at = timezone.now()
        position.raw_data = contract
        position.save(update_fields=["current_price", "profit", "payout", "status", "last_synced_at", "raw_data"])
        return position

    def close_position(self, position, broker_contract=None):
        contract = dict(broker_contract or {})
        if not contract or str(contract.get("contract_id") or "") != str(position.contract_id):
            raise ValueError("A matching broker contract is required before a position can be closed.")

        broker_status = str(contract.get("status") or "").strip().lower()
        if contract.get("is_sold"):
            broker_status = "closed"
        elif contract.get("is_expired"):
            broker_status = "expired"
        if broker_status in {"", "open", "active", "pending"}:
            raise ValueError("The broker has not confirmed a terminal position state.")

        position.status = broker_status
        position.exit_price = contract.get("exit_spot") or contract.get("sell_spot")
        position.profit = contract.get("profit")
        position.payout = contract.get("payout")
        position.closed_at = _broker_datetime(contract.get("sell_spot_time") or contract.get("exit_spot_time"))
        position.settlement_time = _broker_datetime(contract.get("settlement_time"))
        position.raw_data = contract
        position.last_synced_at = timezone.now()
        position.save(update_fields=["status", "exit_price", "profit", "payout", "closed_at", "settlement_time", "raw_data", "last_synced_at"])
        return position

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
        position_sync = await BrokerPositionSyncService().synchronize(broker_account)
        adapter = BrokerRegistry().adapter(broker_account.broker, broker_account)
        positions = position_sync["positions"]
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