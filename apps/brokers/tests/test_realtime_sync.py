from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.brokers.realtime_sync import BrokerRealtimeSync


class BrokerRealtimeSyncTests(SimpleTestCase):
    def _service(self):
        account = SimpleNamespace(
            pk=7,
            account_id="CR123",
            user_id=42,
            broker=SimpleNamespace(broker_type="deriv"),
        )
        with patch("apps.brokers.realtime_sync.BrokerRegistry.adapter", return_value=SimpleNamespace()):
            return BrokerRealtimeSync(account)

    def test_group_name_is_user_scoped(self):
        self.assertEqual(self._service().group_name, "algobot-user-42-broker")

    def test_contract_normalization_preserves_broker_identity(self):
        payload = BrokerRealtimeSync._normalize_contract(
            {
                "contract_id": 991,
                "underlying_symbol": "1HZ100V",
                "contract_type": "CALL",
                "buy_price": 10,
                "bid_price": 12,
                "profit": 2,
                "is_sold": 0,
            }
        )
        self.assertEqual(payload["contract_id"], 991)
        self.assertEqual(payload["symbol"], "1HZ100V")
        self.assertEqual(payload["status"], "open")
        self.assertEqual(payload["profit"], 2)

    def test_sold_contract_is_closed_when_broker_omits_status(self):
        payload = BrokerRealtimeSync._normalize_contract({"contract_id": 992, "is_sold": 1})
        self.assertEqual(payload["status"], "closed")

    def test_transaction_normalization_adds_server_timestamp(self):
        payload = BrokerRealtimeSync._normalize_transaction({"transaction_id": "tx-1"})
        self.assertEqual(payload["transaction"]["transaction_id"], "tx-1")
        self.assertIn("timestamp", payload)
