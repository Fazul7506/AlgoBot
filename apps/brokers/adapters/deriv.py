"""Canonical Deriv broker adapter; vendor-specific behavior lives here."""
import asyncio
import json
import time

import requests
import websockets
from django.conf import settings

from ..exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from .base import BrokerAdapter


class DerivAdapter(BrokerAdapter):
    broker_type = "deriv"
    authentication_type = "oauth"
    supports_streaming = True
    asset_classes = ("synthetics", "forex", "commodities", "crypto", "stock_indices")
    timeout = 10

    @property
    def endpoint(self):
        return settings.DERIV_PUBLIC_WS_URL

    def _token(self):
        if self.account is None or self.account.broker.broker_type != self.broker_type:
            raise BrokerAuthenticationError("A connected Deriv account is required")
        if self.account.token_status != "active" or self.account.is_token_expired:
            raise BrokerAuthenticationError("Deriv credentials are expired or revoked")
        token = self.account.get_access_token()
        if not token:
            raise BrokerAuthenticationError("Deriv access token is unavailable")
        return token

    def _app_id(self):
        app_id = settings.DERIV_APP_ID or settings.DERIV_OAUTH_CLIENT_ID
        if not app_id:
            raise BrokerAuthenticationError("DERIV_APP_ID is not configured")
        return app_id

    def _account_id(self):
        account_id = getattr(self.account, "account_id", None)
        if not account_id:
            raise BrokerAuthenticationError("A verified Deriv account id is required")
        return str(account_id)

    def _authenticated_ws_url(self):
        try:
            response = requests.post(
                f"{settings.DERIV_OPTIONS_ACCOUNTS_URL}/{self._account_id()}/otp",
                headers={"Authorization": f"Bearer {self._token()}", "Deriv-App-ID": self._app_id(), "Accept": "application/json"},
                timeout=(3.05, self.timeout),
            )
            if response.status_code == 401:
                raise BrokerAuthenticationError("Deriv rejected the stored OAuth credential")
            if response.status_code == 403:
                raise BrokerAuthenticationError("Deriv denied trading access for this account")
            response.raise_for_status()
            payload = response.json()
        except BrokerAuthenticationError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise BrokerConnectionError("Unable to obtain an authenticated Deriv WebSocket session") from exc
        url = (payload.get("data") or {}).get("url")
        if not url:
            raise BrokerConnectionError("Deriv did not return an authenticated WebSocket URL")
        return url

    async def _request(self, payload, authenticated=False):
        try:
            endpoint = await asyncio.to_thread(self._authenticated_ws_url) if authenticated else self.endpoint
            async with websockets.connect(endpoint, open_timeout=self.timeout, close_timeout=self.timeout) as ws:
                await ws.send(json.dumps(payload))
                response = json.loads(await asyncio.wait_for(ws.recv(), self.timeout))
        except BrokerAuthenticationError:
            raise
        except (asyncio.TimeoutError, OSError, websockets.WebSocketException, json.JSONDecodeError) as exc:
            raise BrokerConnectionError("Deriv is unavailable or returned an invalid response") from exc
        if response.get("error"):
            message = response["error"].get("message", "Deriv rejected the request")
            code = response["error"].get("code", "")
            if authenticated and code in {"AuthorizationRequired", "InvalidToken", "InvalidAppId", "Unauthorized"}:
                raise BrokerAuthenticationError(message)
            raise BrokerOrderError(message)
        return response

    async def connect(self):
        account = await self.authenticate()
        return {"status": "connected", "account_id": account.get("loginid") or account.get("account_id")}

    async def disconnect(self):
        return {"status": "disconnected"}

    async def authenticate(self):
        response = await self._request({"balance": 1, "req_id": 1}, authenticated=True)
        balance = response.get("balance") or {}
        account_type = str((self.credentials or {}).get("account_type") or "demo").lower()
        return {"loginid": self._account_id(), "account_id": self._account_id(), "balance": balance.get("balance"), "currency": balance.get("currency"), "is_virtual": account_type == "demo"}

    async def refresh_token(self):
        raise BrokerAuthenticationError("Deriv token refresh must be completed through the OAuth flow")

    async def get_accounts(self):
        try:
            response = await asyncio.to_thread(requests.get, settings.DERIV_OPTIONS_ACCOUNTS_URL, headers={"Authorization": f"Bearer {self._token()}", "Deriv-App-ID": self._app_id(), "Accept": "application/json"}, timeout=(3.05, self.timeout))
            if response.status_code in {401, 403}:
                raise BrokerAuthenticationError("Deriv rejected the stored OAuth credential")
            response.raise_for_status()
            data = response.json().get("data", [])
            return data if isinstance(data, list) else [data]
        except BrokerAuthenticationError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise BrokerConnectionError("Unable to retrieve Deriv trading accounts") from exc

    async def get_balance(self):
        account = await self.authenticate()
        return {"account_id": account["account_id"], "balance": account.get("balance"), "currency": account.get("currency"), "account_type": "demo" if account.get("is_virtual") else "real"}

    async def get_positions(self):
        return (await self._request({"portfolio": 1}, authenticated=True)).get("portfolio", {}).get("contracts", [])

    async def get_orders(self):
        return (await self._request({"statement": 1, "limit": 50}, authenticated=True)).get("statement", {}).get("transactions", [])

    async def get_open_orders(self):
        return await self.get_positions()

    async def get_trade_history(self, **filters):
        payload = {"statement": 1, "limit": min(int(filters.get("limit", 50)), 100)}
        for key in ("date_from", "date_to"):
            if filters.get(key) is not None:
                payload[key] = filters[key]
        return (await self._request(payload, authenticated=True)).get("statement", {}).get("transactions", [])

    async def get_market_data(self, symbol, **params):
        tick = (await self._request({"ticks": symbol})).get("tick")
        if not tick:
            raise BrokerConnectionError("Deriv did not return a tick")
        return {"symbol": symbol, "price": tick.get("quote"), "bid": tick.get("bid"), "ask": tick.get("ask"), "epoch": tick.get("epoch")}

    async def subscribe_ticks(self, symbol, callback=None):
        return {"symbol": symbol, "stream": "ticks", "endpoint": self.endpoint}

    async def place_order(self, order):
        routing = order.routing_context or {}
        account_type = str(routing.get("account_type") or self.credentials.get("account_type") or "demo").lower()
        if account_type == "real" and not settings.ALLOW_LIVE_TRADING:
            raise BrokerOrderError("Live-money trading is disabled by platform configuration")
        contract_type = (getattr(order, "contract_type", None) or getattr(order, "direction", None) or "CALL").upper()
        if contract_type in {"BUY", "SELL"}:
            contract_type = str(routing.get("contract_type", "CALL")).upper()
        allowed = {"CALL", "PUT", "MULTUP", "MULTDOWN", "DIGITOVER", "DIGITUNDER", "RISE", "FALL"}
        if contract_type not in allowed:
            raise BrokerOrderError(f"Unsupported Deriv contract type: {contract_type}")
        proposal_payload = {"proposal": 1, "amount": float(order.stake or getattr(order, "quantity", 0)), "basis": "stake", "contract_type": contract_type, "currency": routing.get("currency") or getattr(self.account, "currency", None) or "USD", "duration": int(routing.get("duration", 60)), "duration_unit": routing.get("duration_unit", "s"), "underlying_symbol": order.symbol}
        if routing.get("barrier") is not None: proposal_payload["barrier"] = str(routing["barrier"])
        if routing.get("multiplier") is not None: proposal_payload["multiplier"] = float(routing["multiplier"])
        proposal_response = await self._request(proposal_payload, authenticated=True)
        proposal = proposal_response.get("proposal") or {}
        proposal_id = proposal.get("id")
        ask_price = proposal.get("ask_price") or proposal.get("display_value")
        if not proposal_id or ask_price is None:
            raise BrokerOrderError("Deriv returned an unusable proposal")
        buy = (await self._request({"buy": proposal_id, "price": float(ask_price)}, authenticated=True)).get("buy") or {}
        contract_id = buy.get("contract_id")
        if not contract_id:
            raise BrokerOrderError("Deriv accepted the request without returning a contract ID")
        return {"status": "filled", "broker_order_id": str(contract_id), "execution_price": buy.get("buy_price") or ask_price, "fees": 0, "payout": buy.get("payout"), "proposal_id": proposal_id, "contract_type": contract_type}

    async def modify_order(self, order, **changes):
        raise BrokerOrderError("Deriv contract modification is not exposed by the generic order API")

    async def cancel_order(self, order):
        raise BrokerOrderError("Deriv contracts cannot be cancelled through the generic order API")

    async def close_position(self, position):
        contract_id = getattr(position, "broker_order_id", None)
        if not contract_id:
            raise BrokerOrderError("A Deriv contract id is required to sell a position")
        return await self._request({"sell": int(contract_id), "price": 0}, authenticated=True)

    async def stream_positions(self, callback=None): return {"stream": "portfolio"}
    async def stream_orders(self, callback=None): return {"stream": "transaction"}
    async def stream_prices(self, symbols, callback=None): return {"stream": "ticks", "symbols": list(symbols)}
    async def health_check(self): return {"status": "ok", "latency": await self.ping()}
    async def ping(self):
        start = time.perf_counter()
        await self._request({"ping": 1})
        return (time.perf_counter() - start) * 1000
