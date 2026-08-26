import asyncio
import importlib
import time
from decimal import Decimal
from types import SimpleNamespace

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from . import constants as c
from .exceptions import BrokerRoutingError, BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation


class BrokerRegistry:
    adapter_paths = {'paper': 'apps.brokers.adapters.paper.PaperTradingAdapter', 'deriv': 'apps.brokers.adapters.deriv.DerivAdapter', **{broker: f'apps.brokers.adapters.{broker}.Adapter' for broker in c.SCAFFOLD_BROKERS}}
    def register(self, broker_type, adapter_cls_or_path): self.adapter_paths[broker_type] = adapter_cls_or_path
    def get(self, broker_type):
        target = self.adapter_paths[broker_type]
        if isinstance(target, str):
            module, cls = target.rsplit('.', 1); target = getattr(importlib.import_module(module), cls); self.adapter_paths[broker_type] = target
        return target
    def adapter(self, broker, account=None): return self.get(broker.broker_type)(broker=broker, account=account, credentials=getattr(account, 'credentials', {}) or {})
    def adapter_for_legacy_account(self, account):
        broker_type = str(getattr(getattr(account, 'broker', None), 'slug', '') or getattr(getattr(account, 'broker', None), 'broker_type', '')).lower()
        if broker_type not in self.adapter_paths: raise BrokerRoutingError(f'Unsupported broker type: {broker_type or "unknown"}')
        broker = SimpleNamespace(broker_type=broker_type, name=getattr(getattr(account, 'broker', None), 'name', broker_type))
        return self.get(broker_type)(broker=broker, account=account, credentials=getattr(account, 'credentials', {}) or {})


class BrokerManager:
    broker_catalog = {'deriv': {'name': 'Deriv', 'status': 'active', 'websocket_endpoint': settings.DERIV_PUBLIC_WS_URL, 'supports_live': True, 'auth': 'oauth'}, 'paper': {'name': 'Paper Trading', 'status': 'active', 'supports_live': False, 'auth': 'none'}, 'binance': {'name': 'Binance', 'auth': 'api_key_secret'}, 'bybit': {'name': 'Bybit', 'auth': 'api_key_secret'}, 'oanda': {'name': 'OANDA', 'auth': 'api_token'}, 'interactive_brokers': {'name': 'Interactive Brokers', 'auth': 'session_gateway'}, 'metatrader_gateway': {'name': 'MetaTrader Gateway', 'auth': 'username_password'}, 'dxtrade': {'name': 'DXTrade', 'auth': 'session_token'}, 'ctrader': {'name': 'cTrader', 'auth': 'oauth'}, 'alpaca': {'name': 'Alpaca', 'auth': 'api_key_secret'}, 'forex_com': {'name': 'Forex.com', 'auth': 'username_password'}, 'pepperstone': {'name': 'Pepperstone', 'auth': 'metatrader_or_ctrader'}, 'ic_markets': {'name': 'IC Markets', 'auth': 'metatrader_or_ctrader'}, 'exness': {'name': 'Exness', 'auth': 'api_key_or_session'}}
    def ensure_defaults(self):
        for broker_type, data in self.broker_catalog.items():
            defaults = {'status': data.get('status', 'coming_soon'), 'supports_live': data.get('supports_live', False), 'metadata': {'auth': data['auth'], 'adapter_state': 'production' if broker_type in c.PRODUCTION_BROKERS else 'scaffold'}}
            if data.get('websocket_endpoint'): defaults['websocket_endpoint'] = data['websocket_endpoint']
            Broker.objects.get_or_create(name=data['name'], broker_type=broker_type, defaults=defaults)
    def register_broker(self, broker_type, adapter_path, **metadata): BrokerRegistry().register(broker_type, adapter_path); return metadata
    def enable(self, broker): broker.status = 'active'; broker.save(update_fields=['status']); return broker
    def disable(self, broker): broker.status = 'disabled'; broker.save(update_fields=['status']); return broker
    def select_default_account(self, user): return SmartOrderRouter().route(user, mode='priority')
    async def reconnect(self, broker, account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        await BrokerConnectionService().disconnect(broker, account); return await BrokerConnectionService().connect(broker, account)
    async def monitor_health(self, broker, account=None): return await BrokerConnectionService().heartbeat(broker, account)
    async def failover(self, order): return FailoverService().fallback_account(order)


class BrokerConnectionService:
    async def connect(self, broker, account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        adapter = BrokerRegistry().adapter(broker, account); verification = await adapter.connect(); latency = await adapter.ping()
        if verification.get('account_id') and verification['account_id'] != account.account_id: account.account_id = str(verification['account_id'])
        if verification.get('balance') is not None: account.balance = verification['balance']
        if verification.get('currency'): account.currency = verification['currency']
        account_type = verification.get('is_virtual'); avatar_url = verification.get('avatar_url'); credentials = dict(account.credentials or {})
        if account_type is not None: credentials['account_type'] = 'demo' if account_type else 'real'
        if avatar_url: credentials['avatar_url'] = str(avatar_url)
        account.credentials = credentials; account.status = 'active'; account.last_synced_at = timezone.now()
        await sync_to_async(account.save)(update_fields=['account_id', 'balance', 'currency', 'credentials', 'status', 'last_synced_at'])
        connection, _ = await sync_to_async(BrokerConnection.objects.update_or_create)(broker_account=account, defaults={'broker': broker, 'status': 'connected', 'latency': latency, 'last_ping': timezone.now(), 'connected_at': timezone.now()})
        return connection
    async def disconnect(self, broker, account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        await BrokerRegistry().adapter(broker, account).disconnect(); account.status = 'disabled'
        await sync_to_async(account.save)(update_fields=['status'])
        connection, _ = await sync_to_async(BrokerConnection.objects.update_or_create)(broker_account=account, defaults={'broker': broker, 'status': 'disconnected'})
        return connection
    async def heartbeat(self, broker, account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        adapter = BrokerRegistry().adapter(broker, account); data = await adapter.health_check(); latency = await adapter.ping()
        connection, _ = await sync_to_async(BrokerConnection.objects.update_or_create)(broker_account=account, defaults={'broker': broker, 'status': 'connected', 'latency': latency, 'last_ping': timezone.now(), 'heartbeat': data})
        return connection


class AuthenticationService:
    async def authenticate(self, account): return await BrokerRegistry().adapter(account.broker, account).authenticate()
    async def refresh_token(self, account): return await BrokerRegistry().adapter(account.broker, account).refresh_token()


class LatencyService:
    async def measure(self, broker, account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        latency = await BrokerRegistry().adapter(broker, account).ping()
        await sync_to_async(BrokerConnection.objects.update_or_create)(broker_account=account, defaults={'broker': broker, 'latency': latency, 'last_ping': timezone.now(), 'status': 'connected'})
        return latency


class SmartOrderRouter:
    def route(self, user, symbol=None, mode='latency_based', preferred_account=None):
        qs = BrokerAccount.objects.select_related('broker').filter(user=user, status='active', broker__status='active')
        if preferred_account: qs = qs.filter(pk=preferred_account.pk)
        candidates = [account for account in qs if account.is_connection_eligible]
        if not candidates: raise BrokerRoutingError('No active broker accounts are available')
        if mode == 'priority': return sorted(candidates, key=lambda a: (not a.is_preferred, a.broker.name))[0]
        def score(account):
            conn = BrokerConnection.objects.filter(broker_account=account).order_by('-updated_at').first()
            return (conn.latency if conn else 999999, not account.is_preferred, account.broker.name)
        return sorted(candidates, key=score)[0]


class OrderManagementSystem:
    TERMINAL_STATUSES = {'filled', 'executed', 'partially_filled', 'rejected', 'cancelled', 'expired', 'closed', 'failed', 'reconciled'}
    def create(self, user, **data):
        account = data.get('account') or SmartOrderRouter().route(user, data.get('symbol'))
        if account.user_id != user.id: raise BrokerRoutingError('The selected broker account does not belong to this user')
        if not account.is_connection_eligible: raise BrokerRoutingError('The selected broker account does not have usable broker credentials')
        order = Order.objects.create(user=user, broker=account.broker, account=account, status='created', **{k: v for k, v in data.items() if k != 'account'})
        order.status = 'validated'; order.save(update_fields=['status', 'updated_at']); return order
    def approve(self, order): order.status = 'approved'; order.save(update_fields=['status', 'updated_at']); return order
    def queue(self, order): order.status = 'queued'; order.save(update_fields=['status', 'updated_at']); return order
    def cancel(self, order): order.status = 'cancelled'; order.save(update_fields=['status', 'updated_at']); return order


class ExecutionManagementSystem:
    async def _mark_connection_issue(self, order, state):
        context = dict(order.routing_context or {})
        context['execution_state'] = state
        order.status = 'pending'
        order.routing_context = context
        await sync_to_async(order.save)(update_fields=['status', 'routing_context', 'updated_at'])
        await sync_to_async(BrokerConnection.objects.filter(broker_account=order.account).update)(status='degraded', updated_at=timezone.now())

    async def execute(self, order):
        start = time.perf_counter(); order.status = 'submitted'; order.submitted_at = timezone.now(); await sync_to_async(order.save)(update_fields=['status', 'submitted_at', 'updated_at'])
        adapter = BrokerRegistry().adapter(order.broker, order.account); timeout = float(getattr(settings, 'BROKER_ORDER_TIMEOUT_SECONDS', 20))
        try:
            result = await asyncio.wait_for(adapter.place_order(order), timeout=timeout)
        except asyncio.TimeoutError as exc:
            await self._mark_connection_issue(order, 'unknown_timeout')
            await sync_to_async(TradeReconciliation.objects.create)(broker=order.broker, trade={'order_id': order.pk, 'client_order_id': order.client_order_id, 'state': 'unknown_timeout'}, matched=False, difference={'order': 'broker_response_unknown'}, repaired=False)
            raise BrokerConnectionError('Broker order placement timed out; execution state is unknown and must be reconciled before retrying.') from exc
        except BrokerAuthenticationError:
            order.status = 'rejected'; await sync_to_async(order.save)(update_fields=['status', 'updated_at']); raise
        except BrokerConnectionError:
            await self._mark_connection_issue(order, 'unknown_connection_error')
            await sync_to_async(TradeReconciliation.objects.create)(broker=order.broker, trade={'order_id': order.pk, 'client_order_id': order.client_order_id, 'state': 'unknown_connection_error'}, matched=False, difference={'order': 'broker_response_unknown'}, repaired=False)
            raise
        except BrokerOrderError:
            order.status = 'rejected'; await sync_to_async(order.save)(update_fields=['status', 'updated_at']); raise
        except Exception:
            order.status = 'failed'; await sync_to_async(order.save)(update_fields=['status', 'updated_at']); raise
        latency = (time.perf_counter() - start) * 1000; status_value = 'filled' if result.get('status') in ['filled', 'executed'] else result.get('status', 'executed')
        requested = order.price or Decimal('0'); executed_value = result.get('execution_price'); executed = Decimal(str(executed_value if executed_value is not None else requested or 0)); slippage = executed - requested
        order.status = status_value; order.broker_order_id = str(result.get('broker_order_id', '')); update_fields = ['status', 'broker_order_id', 'updated_at']
        if status_value in {'filled', 'executed', 'partially_filled'}: order.executed_at = timezone.now(); update_fields.append('executed_at')
        await sync_to_async(order.save)(update_fields=update_fields)
        return await sync_to_async(ExecutionReport.objects.create)(order=order, execution_price=executed, requested_price=requested, slippage=slippage, latency=result.get('latency', latency), fees=Decimal(str(result.get('fees', 0))), status=status_value, raw_report=result)


class ExecutionEngine:
    def submit(self, user, **data):
        from apps.risk.engine import RiskEngine

        routing = dict(data.get('routing_context') or {})
        account = data.get('account') or SmartOrderRouter().route(user, data.get('symbol'))
        client_order_id = str(data.get('client_order_id') or '').strip()
        if account.user_id != user.id: raise BrokerRoutingError('The selected broker account does not belong to this user')
        if client_order_id:
            existing = Order.objects.filter(user=user, account=account, client_order_id=client_order_id).order_by('-id').first()
            if existing:
                report = existing.execution_reports.order_by('-id').first()
                if report and existing.status in OrderManagementSystem.TERMINAL_STATUSES: return report
                raise BrokerRoutingError(f'Duplicate client order id {client_order_id}; the existing order is already being processed.')

        if routing.get('ai_assisted'):
            from apps.ai_engine.services import AIEngine
            from apps.market_data.services import MarketDataService
            symbol = data.get('symbol')
            if not symbol: raise BrokerRoutingError('AI-assisted execution requires a broker symbol')
            tick = MarketDataService().history.tick_history(symbol, limit=1).first()
            if tick is None: raise BrokerRoutingError('AI-assisted execution requires fresh normalized market data')
            spread = float(tick.ask - tick.bid) if tick.bid is not None and tick.ask is not None else 0
            ctx = {'market_data': {'close': float(tick.quote), 'open': float(tick.quote), 'high': float(tick.quote), 'low': float(tick.quote), 'spread': spread}}
            analysis = AIEngine().analyze(symbol, routing.get('timeframe', 'M1'), ctx)
            recommendation = analysis['recommendation']
            minimum_confidence = float(routing.get('minimum_ai_confidence', 65))
            if recommendation.confidence < minimum_confidence or recommendation.recommendation == 'WAIT': raise BrokerRoutingError(f'AI gate blocked the order: {recommendation.recommendation} at {recommendation.confidence:.1f}% confidence')
            direction = str(data.get('direction', '')).upper()
            if direction in {'BUY', 'CALL', 'RISE'} and recommendation.recommendation != 'BUY': raise BrokerRoutingError('AI gate rejected a BUY/CALL order')
            if direction in {'SELL', 'PUT', 'FALL'} and recommendation.recommendation != 'SELL': raise BrokerRoutingError('AI gate rejected a SELL/PUT order')
            routing['ai_decision'] = {'recommendation': recommendation.recommendation, 'confidence': recommendation.confidence, 'prediction': analysis['prediction'].prediction}
            routing['ai_consensus'] = (analysis['prediction'].payload or {}).get('consensus', {})
            data['routing_context'] = routing

        data['account'] = account
        try:
            order = OrderManagementSystem().create(user, **data)
        except IntegrityError as exc:
            if client_order_id: raise BrokerRoutingError(f'Duplicate client order id {client_order_id}; the existing order wins the idempotency race.') from exc
            raise

        try:
            RiskEngine().approve_or_raise(order, context={})
        except PermissionError as exc:
            order.status = 'rejected'
            order.routing_context = {**(order.routing_context or {}), 'risk_gate': {'approved': False, 'reason': str(exc)}}
            order.save(update_fields=['status', 'routing_context', 'updated_at'])
            raise BrokerRoutingError(f'Risk gate blocked the order: {exc}') from exc

        order = OrderManagementSystem().queue(OrderManagementSystem().approve(order))
        return asyncio.run(ExecutionManagementSystem().execute(order))


class SynchronizationService:
    async def sync_account(self, account):
        if account.status in {'disabled', 'suspended'}: raise BrokerRoutingError('This broker account is not connected')
        adapter = BrokerRegistry().adapter(account.broker, account); data = await adapter.get_balance(); fields = []; broker_account_id = data.get('account_id') or account.account_id
        if broker_account_id and broker_account_id != account.account_id: account.account_id = broker_account_id; fields.append('account_id')
        for f in ['balance', 'equity', 'margin', 'free_margin', 'currency']:
            if data.get(f) is not None: setattr(account, f, data[f]); fields.append(f)
        credentials = dict(account.credentials or {})
        if data.get('account_type'): credentials['account_type'] = data['account_type']
        if data.get('avatar_url'): credentials['avatar_url'] = str(data['avatar_url'])
        if credentials != (account.credentials or {}): account.credentials = credentials; fields.append('credentials')
        account.status = 'active'; account.last_synced_at = timezone.now(); fields.extend(['status', 'last_synced_at'])
        await sync_to_async(account.save)(update_fields=list(dict.fromkeys(fields)))
        await sync_to_async(BrokerConnection.objects.update_or_create)(broker_account=account, defaults={'broker': account.broker, 'status': 'connected', 'last_ping': timezone.now(), 'connected_at': timezone.now()})
        return account, data


class ReconciliationService:
    def reconcile_order(self, order, broker_trade=None, repair=True):
        expected_reference = str(order.broker_order_id or '')
        observed_reference = str((broker_trade or {}).get('broker_order_id') or (broker_trade or {}).get('order_id') or '')
        matched = bool(expected_reference and observed_reference and expected_reference == observed_reference)
        diff = {} if matched else {'order': 'missing_or_mismatched', 'expected_reference': expected_reference, 'observed_reference': observed_reference}
        rec = TradeReconciliation.objects.create(broker=order.broker, trade=broker_trade or {}, matched=matched, difference=diff, repaired=False)
        if matched:
            if order.status == 'pending':
                order.status = 'reconciled'; order.save(update_fields=['status', 'updated_at'])
        elif repair:
            context = dict(order.routing_context or {})
            context['reconciliation'] = {'required': True, 'difference': diff}
            order.routing_context = context
            order.status = 'pending'
            order.save(update_fields=['status', 'routing_context', 'updated_at'])
        return rec


class BrokerHealthService:
    def summary(self, user=None):
        qs = BrokerAccount.objects.filter(status='active', broker__status='active') if user is None else BrokerAccount.objects.filter(user=user, status='active', broker__status='active')
        connected_qs = qs.filter(connections__status='connected').distinct()
        return {'brokers': qs.values('broker_id').distinct().count(), 'connected': connected_qs.count(), 'accounts': [{'id': a.id, 'broker': a.broker.name, 'account_id': a.account_id, 'status': 'connected' if a.is_connected else 'disconnected', 'last_synced_at': a.last_synced_at.isoformat() if a.last_synced_at else None} for a in qs.select_related('broker')]}


class FailoverService:
    def fallback_account(self, order): return SmartOrderRouter().route(order.user, order.symbol, preferred_account=None)


class AccountService:
    pass


class PositionService:
    def exposure(self, account): return Position.objects.filter(account=account, status='open')
