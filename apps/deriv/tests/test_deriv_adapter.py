from django.test import SimpleTestCase
from apps.deriv.adapter import DerivAdapter

class FakeEngine:
    def __init__(self): self.payloads=[]
    async def request(self, payload): self.payloads.append(payload); return "1"
    async def subscribe(self, symbol): return f"tick-{symbol}"

class DerivAdapterTests(SimpleTestCase):
    async def test_buy_contract_uses_websocket_payload(self):
        engine = FakeEngine(); result = await DerivAdapter(engine=engine).buy_contract(price=1, parameters={})
        self.assertEqual(result["req_id"], "1"); self.assertEqual(engine.payloads[0]["buy"], 1)
    async def test_ticks_delegate_to_engine_subscription(self):
        self.assertEqual(await DerivAdapter(engine=FakeEngine()).ticks("R_100"), "tick-R_100")
