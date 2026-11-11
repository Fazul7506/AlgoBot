import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from apps.brokers.adapters.deriv import DerivAdapter, _account_type_from_is_virtual, _normalize_is_virtual
from apps.brokers.exceptions import BrokerAuthenticationError
from apps.brokers.services import SynchronizationService


class DerivEnvironmentNormalizationTests(SimpleTestCase):
    def test_normalizes_documented_integer_boolean_values(self):
        self.assertIs(_normalize_is_virtual(1), True)
        self.assertIs(_normalize_is_virtual(0), False)
        self.assertIs(_normalize_is_virtual(True), True)
        self.assertIs(_normalize_is_virtual(False), False)
        self.assertEqual(_account_type_from_is_virtual(1), "demo")
        self.assertEqual(_account_type_from_is_virtual(0), "real")

    def test_does_not_guess_unknown_environment_values(self):
        for value in (None, 2, -1, 1.0, "yes", "demo", "", {}):
            with self.subTest(value=value):
                self.assertIsNone(_normalize_is_virtual(value))
                self.assertEqual(_account_type_from_is_virtual(value), "unknown")

    def test_authenticate_normalizes_integer_is_virtual_and_requires_provider_loginid(self):
        async def exercise(value, expected):
            account = SimpleNamespace(account_id="CR123456")
            adapter = DerivAdapter(broker=SimpleNamespace(broker_type="deriv"), account=account)
            adapter._request = AsyncMock(return_value={"balance": {
                "loginid": "CR123456", "balance": "100.00", "currency": "USD", "is_virtual": value,
            }})
            result = await adapter.authenticate()
            self.assertIs(result["is_virtual"], expected)
            self.assertEqual(result["account_id"], "CR123456")
        asyncio.run(exercise(1, True))
        asyncio.run(exercise(0, False))

        async def missing_identity():
            account = SimpleNamespace(account_id="CR123456")
            adapter = DerivAdapter(broker=SimpleNamespace(broker_type="deriv"), account=account)
            adapter._request = AsyncMock(return_value={"balance": {"balance": "100.00", "currency": "USD", "is_virtual": 0}})
            result = await adapter.authenticate()
            self.assertEqual(result["account_id"], "")
        asyncio.run(missing_identity())

    def test_get_balance_maps_deriv_integer_is_virtual_without_using_product_account_type(self):
        async def exercise(is_virtual, expected):
            account = SimpleNamespace(account_id="CR123456")
            adapter = DerivAdapter(broker=SimpleNamespace(broker_type="deriv"), account=account)
            adapter.get_accounts = AsyncMock(return_value=[{
                "account_id": "CR123456", "balance": 100.25, "currency": "USD",
                "is_virtual": is_virtual, "account_type": "trading",
            }])
            result = await adapter.get_balance()
            self.assertEqual(result["account_id"], "CR123456")
            self.assertEqual(result["account_type"], expected)

        asyncio.run(exercise(0, "real"))
        asyncio.run(exercise(1, "demo"))

    def test_get_balance_uses_account_scoped_authorize_when_account_list_environment_is_missing(self):
        async def exercise():
            account = SimpleNamespace(account_id="CR123456")
            adapter = DerivAdapter(broker=SimpleNamespace(broker_type="deriv"), account=account)
            adapter.get_accounts = AsyncMock(return_value=[{
                "account_id": "CR123456", "balance": 100.25, "currency": "USD",
                "is_virtual": None, "account_type": "trading",
            }])
            adapter.authenticate = AsyncMock(return_value={
                "account_id": "CR123456", "balance": 100.25, "currency": "USD", "is_virtual": False,
            })
            result = await adapter.get_balance()
            self.assertEqual(result["account_type"], "real")
            adapter.authenticate.assert_awaited_once()
        asyncio.run(exercise())

    def test_get_balance_rejects_authorize_response_for_another_account(self):
        async def exercise():
            account = SimpleNamespace(account_id="CR123456")
            adapter = DerivAdapter(broker=SimpleNamespace(broker_type="deriv"), account=account)
            adapter.get_accounts = AsyncMock(return_value=[{
                "account_id": "CR123456", "balance": None, "currency": "USD", "is_virtual": None,
            }])
            adapter.authenticate = AsyncMock(return_value={
                "account_id": "VR999999", "balance": 100.25, "currency": "USD", "is_virtual": False,
            })
            with self.assertRaises(BrokerAuthenticationError):
                await adapter.get_balance()
        asyncio.run(exercise())

    def test_snapshot_sync_rejects_missing_or_wrong_provider_account_identity(self):
        async def exercise(payload):
            account = SimpleNamespace(
                status="active", broker=SimpleNamespace(broker_type="deriv"),
                account_id="CR123456", account_type="real",
            )
            adapter = SimpleNamespace(get_balance=AsyncMock(return_value=payload))
            with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
                with self.assertRaises(BrokerAuthenticationError):
                    await SynchronizationService().sync_account(account)
        asyncio.run(exercise({"account_type": "real", "balance": "100.25"}))
        asyncio.run(exercise({"account_id": "VR999999", "account_type": "real", "balance": "100.25"}))

    def test_snapshot_sync_rejects_unknown_environment_without_mutating_account(self):
        async def exercise():
            account = SimpleNamespace(
                status="active", broker=SimpleNamespace(broker_type="deriv"),
                account_id="CR123456", account_type="real",
            )
            adapter = SimpleNamespace(get_balance=AsyncMock(return_value={
                "account_id": "CR123456", "account_type": "unknown", "balance": "100.25",
            }))
            with patch("apps.brokers.services.BrokerRegistry.adapter", return_value=adapter):
                with self.assertRaises(BrokerAuthenticationError):
                    await SynchronizationService().sync_account(account)
            adapter.get_balance.assert_awaited_once()
        asyncio.run(exercise())
