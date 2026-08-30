from types import SimpleNamespace
from unittest.mock import AsyncMock

from django.test import SimpleTestCase

from apps.brokers.deriv_execution import DerivTradingOperations
from apps.brokers.exceptions import BrokerOrderError


class DerivTradingOperationsTests(SimpleTestCase):
    def setUp(self):
        self.account = SimpleNamespace(
            broker=SimpleNamespace(broker_type="deriv"),
            currency="USD",
        )
        self.ops = object.__new__(DerivTradingOperations)
        self.ops.account = self.account
        self.ops.adapter = SimpleNamespace(_request=AsyncMock())

    def test_proposal_uses_current_underlying_symbol_parameter(self):
        self.ops.adapter._request.return_value = {
            "proposal": {"id": "p-1", "ask_price": "1.25", "payout": "2.4"}
        }
        import asyncio
        result = asyncio.run(self.ops.proposal(
            symbol="1HZ100V", contract_type="CALL", amount="10", currency="USD", duration=60
        ))
        payload = self.ops.adapter._request.await_args.args[0]
        self.assertEqual(payload["underlying_symbol"], "1HZ100V")
        self.assertNotIn("symbol", payload)
        self.assertEqual(result["proposal_id"], "p-1")

    def test_buy_requires_contract_id_from_broker(self):
        self.ops.adapter._request.return_value = {"buy": {"contract_id": 123, "buy_price": "10"}}
        import asyncio
        result = asyncio.run(self.ops.buy(proposal_id="p-1", price="10"))
        self.assertEqual(result["contract_id"], "123")

    def test_sell_rejects_negative_price(self):
        import asyncio
        with self.assertRaises(BrokerOrderError):
            asyncio.run(self.ops.sell(contract_id=123, price=-1))

    def test_update_history_uses_contract_id(self):
        self.ops.adapter._request.return_value = {"contract_update_history": {"updates": []}}
        import asyncio
        asyncio.run(self.ops.update_history(123))
        payload = self.ops.adapter._request.await_args.args[0]
        self.assertEqual(payload, {"contract_update_history": 1, "contract_id": 123})
