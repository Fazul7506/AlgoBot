import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from django.test import override_settings

from core.views_broker_oauth import _authorize_deriv_identity_async


class _FakeWebSocket:
    def __init__(self):
        self.send = AsyncMock()
        self.recv = AsyncMock(return_value=json.dumps({
            "authorize": {"loginid": "CR123456", "user_id": 12345}
        }))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class DerivOAuthIdentityEndpointTests(IsolatedAsyncioTestCase):
    @override_settings(
        DERIV_AUTH_WS_BASE_URL="wss://api.derivws.com/trading/v1/options/ws",
        DERIV_PUBLIC_WS_URL="wss://api.derivws.com/trading/v1/options/ws/public",
    )
    async def test_oauth_authorize_uses_authenticated_endpoint_not_public_market_stream(self):
        websocket = _FakeWebSocket()
        with patch(
            "core.views_broker_oauth.websockets.connect",
            return_value=websocket,
        ) as connect:
            identity = await _authorize_deriv_identity_async("test-oauth-token")

        connect.assert_called_once_with(
            "wss://api.derivws.com/trading/v1/options/ws",
            open_timeout=10,
            close_timeout=5,
            ping_interval=None,
        )
        websocket.send.assert_awaited_once_with(json.dumps({
            "authorize": "test-oauth-token",
            "req_id": 1,
        }))
        self.assertEqual(identity["loginid"], "CR123456")
