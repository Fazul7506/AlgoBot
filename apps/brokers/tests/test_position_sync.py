import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.brokers.models import Broker, BrokerAccount, Position
from apps.brokers.position_sync import _persist_snapshot_sync, BrokerPositionSyncService


class PositionSyncPersistenceTests(TransactionTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="position-sync", password="pass")
        self.broker = Broker.objects.create(name="Deriv Sync", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=user,
            broker=self.broker,
            account_id="SYNC-1",
            currency="USD",
            status="active",
        )

    def _position(self, contract_id, status="open"):
        return Position.objects.create(
            broker=self.broker,
            account=self.account,
            contract_id=contract_id,
            symbol="1HZ100V",
            contract_type="CALL",
            stake=Decimal("1"),
            entry_price=Decimal("1"),
            status=status,
        )

    def test_full_snapshot_marks_missing_open_contract_unknown_not_closed(self):
        old = self._position("OLD")
        _persist_snapshot_sync(
            self.account.pk,
            [{
                "contract_id": "NEW",
                "symbol": "1HZ100V",
                "contract_type": "CALL",
                "stake": Decimal("2"),
                "entry_price": Decimal("2"),
                "status": "open",
            }],
            full_snapshot=True,
        )
        old.refresh_from_db()
        self.assertEqual(old.status, "unknown")
        self.assertNotEqual(old.status, "closed")

    def test_synchronize_evaluates_connection_eligibility_outside_async_orm_context(self):
        from apps.brokers.models import BrokerConnection

        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
        )
        adapter = type("Adapter", (), {"get_positions": AsyncMock(return_value=[])})()
        service = BrokerPositionSyncService()
        with (
            patch.object(BrokerAccount, "credential_status", new_callable=PropertyMock, return_value="ready"),
            patch("apps.brokers.position_sync.BrokerRegistry.adapter", return_value=adapter),
        ):
            result = asyncio.run(service.synchronize(self.account))

        self.assertEqual(result["meta"]["status"], "ready")
        adapter.get_positions.assert_awaited_once()

    def test_single_contract_sync_never_closes_unrelated_position(self):
        old = self._position("OLD")
        service = BrokerPositionSyncService()
        asyncio.run(service.synchronize_contract(self.account, {
            "contract_id": "NEW",
            "underlying_symbol": "1HZ100V",
            "contract_type": "CALL",
            "buy_price": "2",
            "currency": "USD",
            "status": "open",
        }))
        old.refresh_from_db()
        self.assertEqual(old.status, "open")
        self.assertTrue(Position.objects.filter(account=self.account, contract_id="NEW").exists())
