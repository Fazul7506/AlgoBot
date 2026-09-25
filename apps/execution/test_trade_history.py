from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from apps.execution.trade_history import normalize_deriv_trade, DerivTradeHistoryService


class DerivTradeHistoryNormalizationTests(SimpleTestCase):
    def test_normalization_preserves_broker_facts_and_nullable_missing_values(self):
        row = normalize_deriv_trade(
            {
                "transaction_id": "TX-1",
                "contract_id": 123,
                "transaction_time": 1760000000,
                "amount": "5",
                "currency": "USD",
            },
            {
                "contract_id": 123,
                "underlying_symbol": "1HZ100V",
                "contract_type": "CALL",
                "buy_price": "5",
                "payout": "9.5",
                "profit": "-5",
                "status": "lost",
                "date_start": 1760000000,
            },
        )
        self.assertEqual(row["broker_contract_id"], "123")
        self.assertEqual(row["broker_transaction_id"], "TX-1")
        self.assertEqual(row["symbol"], "1HZ100V")
        self.assertEqual(row["profit_loss"], Decimal("-5"))
        self.assertEqual(row["payout"], Decimal("9.5"))
        self.assertIsNone(row["sell_price"])
        self.assertEqual(row["currency"], "USD")
        self.assertEqual(row["status"], "lost")
        self.assertIsInstance(row["broker_timestamp"], datetime)
        self.assertEqual(row["broker_timestamp"].tzinfo, timezone.utc)

    def test_missing_identifiers_are_not_invented(self):
        row = normalize_deriv_trade({"amount": "5"}, {})
        self.assertIsNone(row["broker_contract_id"])
        self.assertIsNone(row["broker_transaction_id"])
        self.assertIsNone(row["symbol"])
        self.assertIsNone(row["purchase_time"])

    def test_sold_and_expired_states_use_broker_flags_only(self):
        self.assertEqual(normalize_deriv_trade({"contract_id": 1}, {"contract_id": 1, "is_sold": 1})["status"], "sold")
        self.assertEqual(normalize_deriv_trade({"contract_id": 2}, {"contract_id": 2, "is_expired": 1})["status"], "expired")


class DerivTradeHistoryAdapterBoundaryTests(SimpleTestCase):
    def test_contract_lookup_uses_public_adapter_contract_method(self):
        account = type("Account", (), {"broker": type("Broker", (), {"broker_type": "deriv"})()})()
        service = DerivTradeHistoryService(account)
        adapter = type("Adapter", (), {"get_trade_contract": AsyncMock(return_value={"contract_id": 99})})()
        import asyncio
        result = asyncio.run(service._contract(adapter, 99))
        adapter.get_trade_contract.assert_awaited_once_with(99)
        self.assertEqual(result["contract_id"], 99)
