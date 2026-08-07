import time, uuid
from decimal import Decimal
from django.utils import timezone
from .base import BrokerAdapter
class PaperTradingAdapter(BrokerAdapter):
    broker_type='paper'
    connected=False
    async def connect(self): self.connected=True; return {'status':'connected'}
    async def disconnect(self): self.connected=False; return {'status':'disconnected'}
    async def authenticate(self): return {'status':'authenticated'}
    async def heartbeat(self): return {'status':'ok','timestamp':timezone.now().isoformat()}
    async def get_accounts(self): return [{'account_id': getattr(self.account,'account_id','PAPER-001'), 'currency':'USD'}]
    async def get_balance(self): return {'balance': getattr(self.account,'balance',Decimal('100000')), 'equity': getattr(self.account,'equity',Decimal('100000'))}
    async def get_positions(self): return []
    async def get_orders(self): return []
    async def place_order(self, order):
        return {'broker_order_id': f'PAPER-{uuid.uuid4().hex[:12]}', 'status':'filled', 'execution_price': str(order.price or 1), 'latency': 1.0, 'fees': '0'}
    async def modify_order(self, order, **changes): return {'status':'modified','changes':changes}
    async def cancel_order(self, order): return {'status':'cancelled'}
    async def close_position(self, position): return {'status':'closed'}
    async def get_history(self, **filters): return []
    async def subscribe_ticks(self, symbol, callback=None): return {'subscription':'ticks','symbol':symbol}
    async def subscribe_candles(self, symbol, callback=None): return {'subscription':'candles','symbol':symbol}
    async def subscribe_account(self, callback=None): return {'subscription':'account'}
    async def subscribe_positions(self, callback=None): return {'subscription':'positions'}
    async def ping(self): start=time.perf_counter(); return (time.perf_counter()-start)*1000
