"""Deriv adapter for OAuth-authenticated account data and trading.

Public market streaming remains on DerivWebSocketEngine. Account-scoped
operations use Deriv's short-lived OTP WebSocket URL so OAuth credentials are
never sent to the public market socket.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import requests
import websockets

from .websocket import DerivWebSocketEngine

DERIV_API_BASE = "https://api.derivws.com"
DERIV_ACCOUNTS_URL = f"{DERIV_API_BASE}/trading/v1/options/accounts"


class DerivAdapter:
    def __init__(self, broker_account=None, engine: DerivWebSocketEngine | None = None):
        self.broker_account = broker_account
        self.engine = engine or DerivWebSocketEngine()

    def _token(self) -> str:
        if not self.broker_account or not hasattr(self.broker_account, "token"):
            raise RuntimeError("A connected Deriv OAuth account is required")
        token = self.broker_account.token
        if token.status != "active" or token.is_expired:
            raise RuntimeError("Deriv OAuth token is expired or revoked")
        return token.get_access_token()

    def _app_id(self) -> str:
        app_id = os.getenv("DERIV_APP_ID") or os.getenv("DERIV_OAUTH_CLIENT_ID")
        if not app_id:
            raise RuntimeError("DERIV_APP_ID is not configured")
        return app_id

    def _account_id(self) -> str:
        account_id = getattr(self.broker_account, "broker_account_id", None)
        if not account_id:
            raise RuntimeError("Deriv account id is missing")
        return account_id

    def _otp_url(self) -> str:
        response = requests.post(
            f"{DERIV_ACCOUNTS_URL}/{self._account_id()}/otp",
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Deriv-App-ID": self._app_id(),
                "Accept": "application/json",
            },
            timeout=(3.05, 10),
        )
        if response.status_code in {401, 403}:
            raise RuntimeError("Deriv rejected the OAuth credential or trading permission")
        response.raise_for_status()
        url = (response.json().get("data") or {}).get("url")
        if not url:
            raise RuntimeError("Deriv did not return an authenticated WebSocket URL")
        return url

    async def _authenticated_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = await asyncio.to_thread(self._otp_url)
        async with websockets.connect(url, open_timeout=10, close_timeout=10) as ws:
            await ws.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if response.get("error"):
            raise RuntimeError(response["error"].get("message", "Deriv rejected the request"))
        return response

    async def connect(self) -> dict[str, Any]:
        await self.engine.connect()
        data = await self.balance()
        return {"status": "connected", "account_id": self._account_id(), "balance": data.get("balance")}

    async def disconnect(self) -> None:
        await self.engine.disconnect()

    async def authorize(self) -> str:
        await self._authenticated_request({"balance": 1})
        return self._account_id()

    async def refresh_token(self) -> dict[str, Any]:
        raise RuntimeError("Deriv OAuth token refresh must be completed through the OAuth flow")

    async def balance(self) -> dict[str, Any]:
        response = await self._authenticated_request({"balance": 1})
        return response.get("balance") or {}

    async def portfolio(self):
        return (await self._authenticated_request({"portfolio": 1})).get("portfolio", {})

    async def statement(self, **filters):
        payload = {"statement": 1, **filters}
        return (await self._authenticated_request(payload)).get("statement", {})

    async def profit_table(self, **filters):
        return (await self._authenticated_request({"profit_table": 1, **filters})).get("profit_table", {})

    async def transaction_history(self, **filters):
        return (await self._authenticated_request({"transaction": 1, **filters})).get("transaction", {})

    async def buy_contract(self, **payload):
        return await self._authenticated_request({"buy": 1, **payload})

    async def sell_contract(self, contract_id: str, price: float | None = None):
        payload: dict[str, Any] = {"sell": contract_id}
        if price is not None:
            payload["price"] = price
        return await self._authenticated_request(payload)

    async def proposal(self, **payload):
        return await self._authenticated_request({"proposal": 1, **payload})

    async def proposal_open_contract(self, contract_id: str):
        return await self._authenticated_request({"proposal_open_contract": 1, "contract_id": contract_id})

    async def ticks(self, symbol: str):
        return await self.engine.subscribe(symbol)

    async def candles(self, symbol: str, granularity: int = 60):
        return await self._authenticated_request({"ticks_history": symbol, "style": "candles", "granularity": granularity})

    async def active_symbols(self):
        return await self._authenticated_request({"active_symbols": "brief", "product_type": "basic"})

    async def buy(self, **payload): return await self.buy_contract(**payload)
    async def sell(self, **payload): return await self.sell_contract(**payload)
    async def history(self, **filters): return await self.statement(**filters)
    async def positions(self): return await self.portfolio()
    async def orders(self): return await self.profit_table()
    async def subscribe_ticks(self, symbol: str): return await self.ticks(symbol)
