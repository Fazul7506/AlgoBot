"""Deriv WebSocket adapter.

Deriv's trading API is WebSocket based.  This adapter deliberately does not
inherit from the paper adapter: a broker outage or an unsupported response
must be visible to callers, never converted into a plausible looking value.
"""
import asyncio
import json
import os
import time

import websockets

from ..exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from .base import BrokerAdapter


class DerivAdapter(BrokerAdapter):
    broker_type = "deriv"
    authentication_type = "oauth"
    supports_streaming = True
    asset_classes = ("synthetics", "forex", "commodities", "crypto", "stock_indices")
    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.endpoint = getattr(self.broker, "websocket_endpoint", "") or os.getenv(
            "DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3"
        )

    def _token(self):
        if self.account and hasattr(self.account, "token"):
            token = self.account.token
            if token.status != "active" or token.is_expired:
                raise BrokerAuthenticationError("Deriv credentials are expired or revoked")
            return token.get_access_token()
        token = self.credentials.get("access_token")
        if not token:
            raise BrokerAuthenticationError("A connected Deriv account is required")
        return token

    async def _request(self, payload, authenticated=False):
        """Perform one bounded RPC and validate both protocol and broker errors."""
        try:
            async with websockets.connect(self.endpoint, open_timeout=self.timeout, close_timeout=self.timeout) as ws:
                if authenticated:
                    await ws.send(json.dumps({"authorize": self._token()}))
                    authorization = json.loads(await asyncio.wait_for(ws.recv(), self.timeout))
                    if authorization.get("error"):
                        raise BrokerAuthenticationError(authorization["error"].get("message", "Deriv authorization failed"))
                await ws.send(json.dumps(payload))
                response = json.loads(await asyncio.wait_for(ws.recv(), self.timeout))
        except BrokerAuthenticationError:
            raise
        except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
            raise BrokerConnectionError("Deriv is unavailable or returned an invalid response") from exc
        if response.get("error"):
            raise BrokerOrderError(response["error"].get("message", "Deriv rejected the request"))
        return response

    async def connect(self):
        await self._request({"ping": 1}, authenticated=False)
        return {"status": "connected"}

    async def disconnect(self):
        # RPC connections are request scoped, so there is no shared socket to leak.
        return {"status": "disconnected"}

    async def authenticate(self):
        response = await self._request({"authorize": self._token()}, authenticated=False)
        return response["authorize"]

    async def refresh_token(self):
        raise BrokerAuthenticationError("Deriv token refresh must be completed through the OAuth flow")

    async def get_accounts(self):
        return (await self.authenticate()).get("account_list", [])

    async def get_balance(self):
        account = await self.authenticate()
        result = {
            "account_id": account.get("loginid"), "balance": account.get("balance"),
            "currency": account.get("currency"),
        }
        if "is_virtual" in account:
            result["account_type"] = "demo" if account["is_virtual"] else "real"
        return result

    async def get_positions(self):
        return (await self._request({"portfolio": 1}, authenticated=True)).get("portfolio", {}).get("contracts", [])

    async def get_orders(self):
        return (await self._request({"statement": 1, "limit": 50}, authenticated=True)).get("statement", {}).get("transactions", [])

    async def get_open_orders(self):
        return await self.get_positions()

    async def get_trade_history(self, **filters):
        payload = {"statement": 1, "limit": min(int(filters.get("limit", 50)), 100)}
        if filters.get("date_from") is not None: payload["date_from"] = filters["date_from"]
        if filters.get("date_to") is not None: payload["date_to"] = filters["date_to"]
        return (await self._request(payload, authenticated=True)).get("statement", {}).get("transactions", [])

    async def get_market_data(self, symbol, **params):
        response = await self._request({"ticks": symbol}, authenticated=False)
        tick = response.get("tick")
        if not tick:
            raise BrokerConnectionError("Deriv did not return a tick")
        quote = tick.get("quote")
        return {"symbol": symbol, "price": quote, "bid": tick.get("bid"), "ask": tick.get("ask"), "epoch": tick.get("epoch")}

    async def subscribe_ticks(self, symbol, callback=None):
        # Long-lived subscriptions belong to the ASGI market-data consumer; do
        # not create hidden background sockets in a REST request.
        return {"symbol": symbol, "stream": "ticks", "endpoint": self.endpoint}

    async def place_order(self, order):
        raise BrokerOrderError("Deriv contract execution requires a proposal id and is not available through generic orders")

    async def modify_order(self, order, **changes):
        raise BrokerOrderError("Deriv does not support modifying an executed contract")

    async def cancel_order(self, order):
        raise BrokerOrderError("Deriv contracts cannot be cancelled through the generic order API")

    async def close_position(self, position):
        contract_id = getattr(position, "broker_order_id", None)
        if not contract_id:
            raise BrokerOrderError("A Deriv contract id is required to sell a position")
        return await self._request({"sell": contract_id, "price": 0}, authenticated=True)

    async def stream_positions(self, callback=None): return {"stream": "portfolio"}
    async def stream_orders(self, callback=None): return {"stream": "transaction"}
    async def stream_prices(self, symbols, callback=None): return {"stream": "ticks", "symbols": list(symbols)}

    async def health_check(self):
        return {"status": "ok", "latency": await self.ping()}

    async def ping(self):
        start = time.perf_counter()
        await self._request({"ping": 1})
        return (time.perf_counter() - start) * 1000
