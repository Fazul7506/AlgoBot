from types import SimpleNamespace
from unittest.mock import AsyncMock

from django.test import SimpleTestCase

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.exceptions import BrokerAuthenticationError


class DerivBalanceSyncTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DerivAdapter.__new__(DerivAdapter)
        self.adapter.account = SimpleNamespace(account_id="VRTC123")

    async def test_get_balance_uses_matching_rest_account_without_websocket(self):
        self.adapter.get_accounts = AsyncMock(return_value=[
            {"account_id": "VRTC999", "balance": "1.00", "currency": "USD"},
            {
                "account_id": "VRTC123",
                "balance": "42.50",
                "currency": "EUR",
                "is_virtual": True,
                "avatar_url": "https://example.test/avatar.png",
            },
        ])
        self.adapter.authenticate = AsyncMock()

        result = await self.adapter.get_balance()

        self.assertEqual(result, {
            "account_id": "VRTC123",
            "balance": "42.50",
            "currency": "EUR",
            "account_type": "demo",
            "avatar_url": "https://example.test/avatar.png",
        })
        self.adapter.authenticate.assert_not_awaited()

    async def test_get_balance_falls_back_to_websocket_when_rest_omits_balance(self):
        self.adapter.get_accounts = AsyncMock(return_value=[{"account_id": "VRTC123", "currency": "USD"}])
        self.adapter.authenticate = AsyncMock(return_value={
            "account_id": "VRTC123",
            "balance": "12.00",
            "currency": "USD",
            "is_virtual": False,
            "avatar_url": None,
        })

        result = await self.adapter.get_balance()

        self.assertEqual(result["balance"], "12.00")
        self.assertEqual(result["account_type"], "real")
        self.adapter.authenticate.assert_awaited_once()

    async def test_get_balance_rejects_an_account_missing_from_oauth_scope(self):
        self.adapter.get_accounts = AsyncMock(return_value=[{"account_id": "VRTC999", "balance": "1.00"}])

        with self.assertRaises(BrokerAuthenticationError):
            await self.adapter.get_balance()
