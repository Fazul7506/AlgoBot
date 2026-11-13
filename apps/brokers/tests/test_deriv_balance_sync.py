from types import SimpleNamespace
from unittest.mock import AsyncMock

from django.test import SimpleTestCase

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.exceptions import BrokerAuthenticationError


class DerivBalanceSyncTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DerivAdapter.__new__(DerivAdapter)
        self.adapter.account = SimpleNamespace(
            account_id="VRTC123",
            broker_id=1,
            token_status="active",
            is_token_expired=False,
        )
        self.adapter.broker = SimpleNamespace(broker_type="deriv", pk=1)

    async def test_get_balance_uses_selected_account_otp_authorize_snapshot(self):
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "VRTC123",
            "balance": "42.50",
            "currency": "EUR",
            "is_virtual": True,
            "avatar_url": "https://example.test/avatar.png",
        })
        self.adapter.get_accounts = AsyncMock(
            side_effect=AssertionError("Snapshot must use the selected account OTP session")
        )

        result = await self.adapter.get_balance()

        self.assertEqual(result, {
            "account_id": "VRTC123",
            "balance": "42.50",
            "currency": "EUR",
            "account_type": "demo",
            "avatar_url": "https://example.test/avatar.png",
        })
        self.adapter.authenticate.assert_awaited_once()
        self.adapter.get_accounts.assert_not_awaited()

    async def test_get_balance_maps_authoritative_real_account(self):
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "VRTC123",
            "balance": "12.00",
            "currency": "USD",
            "is_virtual": False,
            "avatar_url": None,
        })

        result = await self.adapter.get_balance()

        self.assertEqual(result["account_type"], "real")
        self.assertEqual(result["account_id"], "VRTC123")

    async def test_unknown_account_type_is_not_inferred_as_real_or_demo(self):
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "VRTC123",
            "balance": "12.00",
            "currency": "USD",
            "is_virtual": None,
            "avatar_url": None,
        })

        result = await self.adapter.get_balance()

        self.assertEqual(result["account_type"], "unknown")

    async def test_get_balance_rejects_authorize_response_for_another_account(self):
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "VRTC999",
            "balance": "1.00",
            "currency": "USD",
            "is_virtual": True,
            "avatar_url": None,
        })

        with self.assertRaises(BrokerAuthenticationError):
            await self.adapter.get_balance()

    async def test_get_balance_rejects_missing_provider_account_identity(self):
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "",
            "balance": "1.00",
            "currency": "USD",
            "is_virtual": True,
            "avatar_url": None,
        })

        with self.assertRaises(BrokerAuthenticationError):
            await self.adapter.get_balance()
