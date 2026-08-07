import asyncio, time
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .adapters.deriv import DerivAdapter
from .adapters.paper import PaperTradingAdapter
from .exceptions import BrokerRoutingError
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation

class BrokerRegistry:
    adapters={'deriv':DerivAdapter,'paper':PaperTradingAdapter}
    def register(self, broker_type, adapter_cls): self.adapters[broker_type]=adapter_cls
    def get(self, broker_type): return self.adapters[broker_type]
    def adapter(self, broker, account=None): return self.get(broker.broker_type)(broker=broker, account=account, credentials=getattr(account,'credentials',{}))
class BrokerManager:
    def ensure_defaults(self):
        Broker.objects.get_or_create(name='Deriv', broker_type='deriv', defaults={'websocket_endpoint':'wss://ws.derivws.com/websockets/v3','supports_live':True})
        Broker.objects.get_or_create(name='Paper Trading', broker_type='paper', defaults={'supports_live':False})
class BrokerConnectionService:
    async def connect(self, broker):
        adapter=BrokerRegistry().adapter(broker); await adapter.connect(); latency=await adapter.ping()
        return BrokerConnection.objects.update_or_create(broker=broker, defaults={'status':'connected','latency':latency,'last_ping':timezone.now(),'connected_at':timezone.now()})[0]
    async def disconnect(self, broker):
        await BrokerRegistry().adapter(broker).disconnect(); conn,_=BrokerConnection.objects.update_or_create(broker=broker, defaults={'status':'disconnected'}); return conn
    async def heartbeat(self, broker):
        adapter=BrokerRegistry().adapter(broker); data=await adapter.heartbeat(); latency=await adapter.ping(); conn,_=BrokerConnection.objects.update_or_create(broker=broker, defaults={'status':'connected','latency':latency,'last_ping':timezone.now(),'heartbeat':data}); return conn
class AuthenticationService:
    async def authenticate(self, account): return await BrokerRegistry().adapter(account.broker, account).authenticate()
class LatencyService:
    async def measure(self, broker):
        latency=await BrokerRegistry().adapter(broker).ping(); BrokerConnection.objects.update_or_create(broker=broker, defaults={'latency':latency,'last_ping':timezone.now(),'status':'connected'}); return latency
class SmartOrderRouter:
    def route(self, user, symbol=None, mode='latency_based', preferred_account=None):
        qs=BrokerAccount.objects.select_related('broker').filter(user=user,status='active',broker__status='active')
        if preferred_account: qs=qs.filter(pk=preferred_account.pk)
        candidates=list(qs)
        if not candidates: raise BrokerRoutingError('No active broker accounts are available')
        if mode=='priority': return sorted(candidates, key=lambda a: (not a.is_preferred, a.broker.name))[0]
        def score(a):
            conn=BrokerConnection.objects.filter(broker=a.broker).order_by('-updated_at').first()
            return (conn.latency if conn else 999999, not a.is_preferred, a.broker.name)
        return sorted(candidates, key=score)[0]
class OrderManagementSystem:
    def create(self, user, **data):
        account=data.get('account') or SmartOrderRouter().route(user, data.get('symbol'))
        order=Order.objects.create(user=user, broker=account.broker, account=account, status='created', **{k:v for k,v in data.items() if k!='account'})
        order.status='validated'; order.save(update_fields=['status','updated_at']); return order
    def approve(self, order): order.status='approved'; order.save(update_fields=['status','updated_at']); return order
    def queue(self, order): order.status='queued'; order.save(update_fields=['status','updated_at']); return order
    def cancel(self, order): order.status='cancelled'; order.save(update_fields=['status','updated_at']); return order
class ExecutionManagementSystem:
    async def execute(self, order):
        start=time.perf_counter(); order.status='submitted'; order.submitted_at=timezone.now(); order.save(update_fields=['status','submitted_at','updated_at'])
        result=await BrokerRegistry().adapter(order.broker, order.account).place_order(order)
        latency=(time.perf_counter()-start)*1000; status='filled' if result.get('status') in ['filled','executed'] else result.get('status','executed')
        requested=order.price or Decimal('0'); executed=Decimal(str(result.get('execution_price') or requested or 0)); slippage=executed-requested
        order.status=status; order.broker_order_id=result.get('broker_order_id',''); order.executed_at=timezone.now(); order.save(update_fields=['status','broker_order_id','executed_at','updated_at'])
        return ExecutionReport.objects.create(order=order, execution_price=executed, requested_price=requested, slippage=slippage, latency=result.get('latency',latency), fees=Decimal(str(result.get('fees',0))), status=status, raw_report=result)
class ExecutionEngine:
    def submit(self, user, **data):
        order=OrderManagementSystem().queue(OrderManagementSystem().approve(OrderManagementSystem().create(user, **data)))
        return asyncio.run(ExecutionManagementSystem().execute(order))
class SynchronizationService:
    async def sync_account(self, account):
        data=await BrokerRegistry().adapter(account.broker, account).get_balance();
        for f in ['balance','equity','margin','free_margin']:
            if f in data: setattr(account, f, data[f])
        account.last_synced_at=timezone.now(); account.save(); return account
class ReconciliationService:
    def reconcile_order(self, order, broker_trade=None, repair=True):
        diff={} if broker_trade and broker_trade.get('broker_order_id')==order.broker_order_id else {'order':'missing_or_mismatched'}
        rec=TradeReconciliation.objects.create(broker=order.broker, trade=broker_trade or {}, matched=not diff, difference=diff, repaired=bool(diff and repair))
        if rec.repaired: order.status='reconciled'; order.save(update_fields=['status','updated_at'])
        return rec
class BrokerHealthService:
    def summary(self): latencies=list(BrokerConnection.objects.filter(status='connected').values_list('latency', flat=True)); return {'brokers':Broker.objects.count(),'connected':len(latencies),'average_latency':(sum(latencies)/len(latencies) if latencies else 0),'broker_rankings':latencies}
class FailoverService:
    def fallback_account(self, order): return SmartOrderRouter().route(order.user, order.symbol, preferred_account=None)
class AccountService: pass
class PositionService:
    def exposure(self, account): return Position.objects.filter(account=account,status='open')
