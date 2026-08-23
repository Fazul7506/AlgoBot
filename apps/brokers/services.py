import asyncio, importlib, time
from decimal import Decimal
from types import SimpleNamespace
from django.conf import settings
from django.utils import timezone
from . import constants as c
from .exceptions import BrokerRoutingError
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation

class BrokerRegistry:
    adapter_paths={'paper':'apps.brokers.adapters.paper.PaperTradingAdapter','deriv':'apps.brokers.adapters.deriv.DerivAdapter',**{broker:f'apps.brokers.adapters.{broker}.Adapter' for broker in c.SCAFFOLD_BROKERS}}
    def register(self,broker_type,adapter_cls_or_path): self.adapter_paths[broker_type]=adapter_cls_or_path
    def get(self,broker_type):
        target=self.adapter_paths[broker_type]
        if isinstance(target,str):
            module,cls=target.rsplit('.',1); target=getattr(importlib.import_module(module),cls); self.adapter_paths[broker_type]=target
        return target
    def adapter(self,broker,account=None): return self.get(broker.broker_type)(broker=broker,account=account,credentials=getattr(account,'credentials',{}))
    def adapter_for_legacy_account(self, account):
        """Bridge old persisted accounts to the canonical adapter without a second broker implementation."""
        broker_type = str(getattr(getattr(account, 'broker', None), 'slug', '') or getattr(getattr(account, 'broker', None), 'broker_type', '')).lower()
        if broker_type not in self.adapter_paths:
            raise BrokerRoutingError(f'Unsupported broker type: {broker_type or "unknown"}')
        broker = SimpleNamespace(broker_type=broker_type, name=getattr(getattr(account, 'broker', None), 'name', broker_type))
        return self.get(broker_type)(broker=broker, account=account, credentials=getattr(account, 'credentials', {}) or {})

class BrokerManager:
    broker_catalog={'deriv':{'name':'Deriv','status':'active','websocket_endpoint':settings.DERIV_PUBLIC_WS_URL,'supports_live':True,'auth':'oauth'},'paper':{'name':'Paper Trading','status':'active','supports_live':False,'auth':'none'},'binance':{'name':'Binance','auth':'api_key_secret'},'bybit':{'name':'Bybit','auth':'api_key_secret'},'oanda':{'name':'OANDA','auth':'api_token'},'interactive_brokers':{'name':'Interactive Brokers','auth':'session_gateway'},'metatrader_gateway':{'name':'MetaTrader Gateway','auth':'username_password'},'dxtrade':{'name':'DXTrade','auth':'session_token'},'ctrader':{'name':'cTrader','auth':'oauth'},'alpaca':{'name':'Alpaca','auth':'api_key_secret'},'forex_com':{'name':'Forex.com','auth':'username_password'},'pepperstone':{'name':'Pepperstone','auth':'metatrader_or_ctrader'},'ic_markets':{'name':'IC Markets','auth':'metatrader_or_ctrader'},'exness':{'name':'Exness','auth':'api_key_or_session'}}
    def ensure_defaults(self):
        for broker_type,data in self.broker_catalog.items():
            defaults={'status':data.get('status','coming_soon'),'supports_live':data.get('supports_live',False),'metadata':{'auth':data['auth'],'adapter_state':'production' if broker_type in c.PRODUCTION_BROKERS else 'scaffold'}}
            if data.get('websocket_endpoint'): defaults['websocket_endpoint']=data['websocket_endpoint']
            Broker.objects.get_or_create(name=data['name'],broker_type=broker_type,defaults=defaults)
    def register_broker(self,broker_type,adapter_path,**metadata): BrokerRegistry().register(broker_type,adapter_path); return metadata
    def enable(self,broker): broker.status='active'; broker.save(update_fields=['status']); return broker
    def disable(self,broker): broker.status='disabled'; broker.save(update_fields=['status']); return broker
    def select_default_account(self,user): return SmartOrderRouter().route(user,mode='priority')
    async def reconnect(self,broker,account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        await BrokerConnectionService().disconnect(broker,account); return await BrokerConnectionService().connect(broker,account)
    async def monitor_health(self,broker,account=None): return await BrokerConnectionService().heartbeat(broker,account)
    async def failover(self,order): return FailoverService().fallback_account(order)

class BrokerConnectionService:
    async def connect(self,broker,account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        adapter=BrokerRegistry().adapter(broker,account); verification=await adapter.connect(); latency=await adapter.ping()
        if verification.get('account_id') and verification['account_id'] != account.account_id: account.account_id=str(verification['account_id'])
        if verification.get('balance') is not None: account.balance=verification['balance']
        if verification.get('currency'): account.currency=verification['currency']
        account_type=verification.get('is_virtual'); credentials=dict(account.credentials or {})
        if account_type is not None: credentials['account_type']='demo' if account_type else 'real'
        account.credentials=credentials; account.status='active'; account.last_synced_at=timezone.now(); account.save(update_fields=['account_id','balance','currency','credentials','status','last_synced_at'])
        return BrokerConnection.objects.update_or_create(broker=broker,defaults={'status':'connected','latency':latency,'last_ping':timezone.now(),'connected_at':timezone.now()})[0]
    async def disconnect(self,broker,account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        await BrokerRegistry().adapter(broker,account).disconnect(); account.status='disconnected'; account.save(update_fields=['status']); return BrokerConnection.objects.update_or_create(broker=broker,defaults={'status':'disconnected'})[0]
    async def heartbeat(self,broker,account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        adapter=BrokerRegistry().adapter(broker,account); data=await adapter.health_check(); latency=await adapter.ping(); return BrokerConnection.objects.update_or_create(broker=broker,defaults={'status':'connected','latency':latency,'last_ping':timezone.now(),'heartbeat':data})[0]
class AuthenticationService:
    async def authenticate(self,account): return await BrokerRegistry().adapter(account.broker,account).authenticate()
    async def refresh_token(self,account): return await BrokerRegistry().adapter(account.broker,account).refresh_token()
class LatencyService:
    async def measure(self,broker,account=None):
        if account is None: raise BrokerRoutingError('An account-scoped broker connection is required')
        latency=await BrokerRegistry().adapter(broker,account).ping(); BrokerConnection.objects.update_or_create(broker=broker,defaults={'latency':latency,'last_ping':timezone.now(),'status':'connected'}); return latency
class SmartOrderRouter:
    def route(self,user,symbol=None,mode='latency_based',preferred_account=None):
        qs=BrokerAccount.objects.select_related('broker').filter(user=user,status='active',broker__status='active')
        if preferred_account: qs=qs.filter(pk=preferred_account.pk)
        candidates=list(qs)
        if not candidates: raise BrokerRoutingError('No active broker accounts are available')
        if mode=='priority': return sorted(candidates,key=lambda a:(not a.is_preferred,a.broker.name))[0]
        def score(a):
            conn=BrokerConnection.objects.filter(broker=a.broker).order_by('-updated_at').first(); return (conn.latency if conn else 999999,not a.is_preferred,a.broker.name)
        return sorted(candidates,key=score)[0]
class OrderManagementSystem:
    def create(self,user,**data):
        account=data.get('account') or SmartOrderRouter().route(user,data.get('symbol'))
        if account.user_id!=user.id: raise BrokerRoutingError('The selected broker account does not belong to this user')
        order=Order.objects.create(user=user,broker=account.broker,account=account,status='created',**{k:v for k,v in data.items() if k!='account'}); order.status='validated'; order.save(update_fields=['status','updated_at']); return order
    def approve(self,order): order.status='approved'; order.save(update_fields=['status','updated_at']); return order
    def queue(self,order): order.status='queued'; order.save(update_fields=['status','updated_at']); return order
    def cancel(self,order): order.status='cancelled'; order.save(update_fields=['status','updated_at']); return order
class ExecutionManagementSystem:
    async def execute(self,order):
        start=time.perf_counter(); order.status='submitted'; order.submitted_at=timezone.now(); order.save(update_fields=['status','submitted_at','updated_at'])
        try: result=await BrokerRegistry().adapter(order.broker,order.account).place_order(order)
        except Exception: order.status='rejected'; order.save(update_fields=['status','updated_at']); raise
        latency=(time.perf_counter()-start)*1000; status='filled' if result.get('status') in ['filled','executed'] else result.get('status','executed'); requested=order.price or Decimal('0'); executed=Decimal(str(result.get('execution_price') or requested or 0)); slippage=executed-requested; order.status=status; order.broker_order_id=result.get('broker_order_id',''); order.executed_at=timezone.now(); order.save(update_fields=['status','broker_order_id','executed_at','updated_at']); return ExecutionReport.objects.create(order=order,execution_price=executed,requested_price=requested,slippage=slippage,latency=result.get('latency',latency),fees=Decimal(str(result.get('fees',0))),status=status,raw_report=result)
class ExecutionEngine:
    def submit(self,user,**data):
        routing=dict(data.get('routing_context') or {})
        if routing.get('ai_assisted'):
            from apps.ai_engine.services import AIEngine
            from apps.market_data.services import MarketDataService
            symbol=data.get('symbol')
            if not symbol: raise BrokerRoutingError('AI-assisted execution requires a broker symbol')
            tick=MarketDataService().history.tick_history(symbol, limit=1).first()
            if tick is None: raise BrokerRoutingError('AI-assisted execution requires fresh normalized market data')
            spread=float(tick.ask-tick.bid) if tick.bid is not None and tick.ask is not None else 0
            ctx={'market_data':{'close':float(tick.quote),'open':float(tick.quote),'high':float(tick.quote),'low':float(tick.quote),'spread':spread}}
            analysis=AIEngine().analyze(symbol,routing.get('timeframe','M1'),ctx); recommendation=analysis['recommendation']; minimum_confidence=float(routing.get('minimum_ai_confidence',65))
            if recommendation.confidence<minimum_confidence or recommendation.recommendation=='WAIT': raise BrokerRoutingError(f'AI gate blocked the order: {recommendation.recommendation} at {recommendation.confidence:.1f}% confidence')
            direction=str(data.get('direction','')).upper()
            if direction in {'BUY','CALL','RISE'} and recommendation.recommendation!='BUY': raise BrokerRoutingError('AI gate rejected a BUY/CALL order')
            if direction in {'SELL','PUT','FALL'} and recommendation.recommendation!='SELL': raise BrokerRoutingError('AI gate rejected a SELL/PUT order')
            routing['ai_decision']={'recommendation':recommendation.recommendation,'confidence':recommendation.confidence,'prediction':analysis['prediction'].prediction}; data['routing_context']=routing
        order=OrderManagementSystem().queue(OrderManagementSystem().approve(OrderManagementSystem().create(user,**data))); return asyncio.run(ExecutionManagementSystem().execute(order))
class SynchronizationService:
    async def sync_account(self,account):
        if account.status in {'disconnected','revoked'}: raise BrokerRoutingError('This broker account is not connected')
        adapter=BrokerRegistry().adapter(account.broker,account); data=await adapter.get_balance(); fields=[]; broker_account_id=data.get('account_id') or account.account_id
        if broker_account_id and broker_account_id!=account.account_id: account.account_id=broker_account_id; fields.append('account_id')
        for f in ['balance','equity','margin','free_margin','currency']:
            if data.get(f) is not None: setattr(account,f,data[f]); fields.append(f)
        if data.get('account_type'):
            credentials=dict(account.credentials or {}); credentials['account_type']=data['account_type']; account.credentials=credentials; fields.append('credentials')
        account.status='active'; account.last_synced_at=timezone.now(); fields.extend(['status','last_synced_at']); account.save(update_fields=list(dict.fromkeys(fields)))
        BrokerConnection.objects.update_or_create(broker=account.broker,defaults={'status':'connected','last_ping':timezone.now(),'connected_at':timezone.now()}); return account,data
class ReconciliationService:
    def reconcile_order(self,order,broker_trade=None,repair=True):
        diff={} if broker_trade and broker_trade.get('broker_order_id')==order.broker_order_id else {'order':'missing_or_mismatched'}; rec=TradeReconciliation.objects.create(broker=order.broker,trade=broker_trade or {},matched=not diff,difference=diff,repaired=bool(diff and repair));
        if rec.repaired: order.status='reconciled'; order.save(update_fields=['status','updated_at'])
        return rec
class BrokerHealthService:
    def summary(self,user=None):
        qs=BrokerAccount.objects.filter(status='active',broker__status='active') if user is None else BrokerAccount.objects.filter(user=user,status='active',broker__status='active'); return {'brokers':qs.values('broker_id').distinct().count(),'connected':qs.count(),'accounts':[{'id':a.id,'broker':a.broker.name,'account_id':a.account_id,'status':a.status,'last_synced_at':a.last_synced_at.isoformat() if a.last_synced_at else None} for a in qs.select_related('broker')]}
class FailoverService:
    def fallback_account(self,order): return SmartOrderRouter().route(order.user,order.symbol,preferred_account=None)
class AccountService: pass
class PositionService:
    def exposure(self,account): return Position.objects.filter(account=account,status='open')
