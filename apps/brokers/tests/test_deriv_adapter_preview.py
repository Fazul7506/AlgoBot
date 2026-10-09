from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.exceptions import BrokerOrderError


class DerivAdapterPreviewTests(IsolatedAsyncioTestCase):
    def make_adapter(self):
        account = SimpleNamespace(
            broker=SimpleNamespace(broker_type="deriv"),
            currency="USD",
        )
        adapter = DerivAdapter(broker=account.broker, account=account)
        adapter._request = AsyncMock(return_value={
            "proposal": {
                "id": "proposal-demo-only",
                "ask_price": "1.00",
                "payout": "1.90",
                "spot": "100.25",
            }
        })
        return adapter

    async def test_preview_returns_broker_priced_estimate_without_buying(self):
        adapter = self.make_adapter()

        result = await adapter.get_order_preview(
            symbol="R_100",
            contract_type="CALL",
            amount="1.00",
            duration=60,
            duration_unit="s",
        )

        self.assertEqual(result["proposal_id"], "proposal-demo-only")
        self.assertEqual(result["ask_price"], "1.00")
        self.assertEqual(result["payout"], "1.90")
        self.assertEqual(result["symbol"], "R_100")
        self.assertEqual(result["contract_type"], "CALL")
        adapter._request.assert_awaited_once_with({
            "proposal": 1,
            "amount": 1.0,
            "basis": "stake",
            "contract_type": "CALL",
            "currency": "USD",
            "duration": 60,
            "duration_unit": "s",
            "underlying_symbol": "R_100",
        }, authenticated=True)
        self.assertNotIn("buy", adapter._request.await_args.args[0])

    async def test_preview_rejects_invalid_stake_before_broker_request(self):
        adapter = self.make_adapter()

        with self.assertRaises(BrokerOrderError):
            await adapter.get_order_preview(
                symbol="R_100",
                contract_type="CALL",
                amount="0",
                duration=60,
                duration_unit="s",
            )

        adapter._request.assert_not_awaited()

    async def test_preview_rejects_incomplete_broker_proposal(self):
        adapter = self.make_adapter()
        adapter._request.return_value = {"proposal": {"id": "proposal-demo-only"}}

        with self.assertRaises(BrokerOrderError):
            await adapter.get_order_preview(
                symbol="R_100",
                contract_type="CALL",
                amount="1.00",
                duration=60,
                duration_unit="s",
            )
