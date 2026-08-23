"""Deriv broker adapter using the WebSocket trading API."""
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
        self.endpoint = getattr(self.broker, "websocket_endpoint", "") or os.getenv("DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3")

    def _token(self):
        """Read the encrypted token from the verified DerivAccount linked to the broker account."""
        if self.account is not None:
            try:
                deriv_account = self.account.user.deriv_account
            except Exception as exc:
                raise BrokerAuthenticationError("A verified Deriv account is required") from exc
            if deriv_account.token_status != "active" or deriv_account.is_token_expired:
                raise BrokerAuthenticationError("Deriv credentials are expired or revoked")
            return deriv_account.get_access_token()
        raise BrokerAuthenticationError("A connected Deriv account is required")

    async def _request(self, payload, authenticated=False):
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
        """Verify the actual broker credential, not just public network reachability."""
        account = await self.authenticate()
        return {"status": "connected", "account_id": account.get("loginid")}

    async def disconnect(self):
        return {"status": "disconnected"}

    async def authenticate(self):
        response = await self._request({"authorize": self._token()})
        return response["authorize"]

    async def refresh_token(self):
        raise BrokerAuthenticationError("Deriv token refresh must be completed through the OAuth flow")

    async def get_accounts(self):
        return (await self.authenticate()).get("account_list", [])

    async def get_balance(self):
        account = await self.authenticate()
        return {"account_id": account.get("loginid"), "balance": account.get("balance"), "currency": account.get("currency"), "account_type": "demo" if account.get("is_virtual") else "real"}

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
        response = await self._request({"ticks": symbol})
        tick = response.get("tick")
        if not tick:
            raise BrokerConnectionError("Deriv did not return a tick")
        return {"symbol": symbol, "price": tick.get("quote"), "bid": tick.get("bid"), "ask": tick.get("ask"), "epoch": tick.get("epoch")}

    async def subscribe_ticks(self, symbol, callback=None):
        return {"symbol": symbol, "stream": "ticks", "endpoint": self.endpoint}

    async def place_order(self, order):
        """Get a live proposal and buy it; no simulated fills are returned."""
        routing = order.routing_context or {}
        account_type = str(routing.get("account_type") or self.credentials.get("account_type") or "demo").lower()
        if account_type == "real" and os.getenv("ALLOW_LIVE_TRADING", "false").lower() not in {"1", "true", "yes"}:
            raise BrokerOrderError("Live-money trading is disabled. Set ALLOW_LIVE_TRADING=true only after production risk validation.")

        contract_type = (order.contract_type or order.direction or "CALL").upper()
        if contract_type in {"BUY", "SELL"}:
            contract_type = routing.get("contract_type", "CALL").upper()
        if contract_type not in {"CALL", "PUT", "MULTUP", "MULTDOWN", "DIGITOVER", "DIGITUNDER", "RISE", "FALL"}:
            raise BrokerOrderError(f"Unsupported Deriv contract type: {contract_type}")

        duration = int(routing.get("duration", 60))
        duration_unit = routing.get("duration_unit", "s")
        currency = routing.get("currency") or getattr(self.account, "currency", None) or "USD"
        proposal_payload = {
            "proposal": 1,
            "amount": float(order.stake or order.quantity),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": currency,
            "duration": duration,
            "duration_unit": duration_unit,
            "underlying_symbol": order.symbol,
        }
        if routing.get("barrier") is not None:
            proposal_payload["barrier"] = str(routing["barrier"])
        if routing.get("multiplier") is not None:
            proposal_payload["multiplier"] = float(routing["multiplier"])

        proposal_response = await self._request(proposal_payload, authenticated=True)
        proposal = proposal_response.get("proposal") or {}
        proposal_id = proposal.get("id")
        ask_price = proposal.get("ask_price") or proposal.get("display_value")
        if not proposal_id or ask_price is None:
            raise BrokerOrderError("Deriv returned an unusable proposal")

        buy_response = await self._request({"buy": proposal_id, "price": float(ask_price)}, authenticated=True)
        buy = buy_response.get("buy") or {}
        contract_id = buy.get("contract_id")
        if not contract_id:
            raise BrokerOrderError("Deriv accepted the request without returning a contract ID")
        return {
            "status": "filled",
            "broker_order_id": str(contract_id),
            "execution_price": buy.get("buy_price") or ask_price,
            "fees": 0,
            "payout": buy.get("payout"),
            "proposal_id": proposal_id,
            "contract_type": contract_type,
            "raw": {"proposal": proposal_response, "buy": buy_response},
        }

    async def modify_order(self, order, **changes):
        raise BrokerOrderError("Deriv contract modification requires a contract_update operation and explicit contract id")

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
