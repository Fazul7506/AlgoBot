import asyncio
from types import SimpleNamespace

from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount

from apps.brokers.realtime_sync import BrokerRealtimeSync


class BrokerRealtimeSyncTests(SimpleTestCase):
    def _service(self):
        account = SimpleNamespace(
            pk=7,
            account_id="CR123",
            user_id=42,
            broker=SimpleNamespace(broker_type="deriv"),
        )
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

    def test_account_stream_includes_all_open_contracts_subscription(self):
        service = self._service()
        service.adapter = SimpleNamespace()
        captured = {}

        async def fake_stream(subscriptions, **kwargs):
            captured["subscriptions"] = subscriptions

        service.adapter._stream = fake_stream
        asyncio.run(service._run_account_stream())
        self.assertIn(
            {"proposal_open_contract": 1, "subscribe": 1, "req_id": 1004},
            captured["subscriptions"],
        )


class BrokerRealtimeFinancialSnapshotTests(TransactionTestCase):
    def setUp(self):
        broker = Broker.objects.create(name="Realtime Snapshot Test", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user_id=1,
            broker=broker,
            account_id="CR-SNAPSHOT-1",
            status="active",
            credentials={"account_type": "demo"},
        )
        self.service = BrokerRealtimeSync(self.account)

    def test_balance_event_marks_only_fields_actually_supplied_by_broker(self):
        asyncio.run(self.service._sync_balance({
            "loginid": "CR-SNAPSHOT-1",
            "balance": "5902.30",
            "currency": "USD",
        }))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("5902.30"))
        self.assertEqual(
            self.account.credentials["financial_snapshot_fields"],
            ["balance", "currency"],
        )
        self.assertIsNotNone(self.account.last_synced_at)
        self.assertNotIn("equity", self.account.credentials["financial_snapshot_fields"])
        self.assertNotIn("free_margin", self.account.credentials["financial_snapshot_fields"])

    def test_currency_only_event_does_not_refresh_the_balance_snapshot_timestamp(self):
        previous_sync = timezone.now() - timezone.timedelta(minutes=5)
        self.account.last_synced_at = previous_sync
        self.account.save(update_fields=["last_synced_at"])
        asyncio.run(self.service._sync_balance({
            "loginid": "CR-SNAPSHOT-1",
            "currency": "USD",
        }))
        self.account.refresh_from_db()
        self.assertEqual(self.account.last_synced_at, previous_sync)
        self.assertNotIn("balance", self.account.credentials.get("financial_snapshot_fields", []))
