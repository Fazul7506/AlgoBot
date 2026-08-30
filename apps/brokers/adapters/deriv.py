"""Canonical Deriv broker adapter; vendor-specific behavior lives here."""
import asyncio
import inspect
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
            async with websockets.connect(endpoint, open_timeout=self.timeout, close_timeout=self.timeout, ping_interval=20, ping_timeout=10) as ws:
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

    async def _dispatch_stream(self, callback, message):
        if callback is None:
            return
        result = callback(message)
        if inspect.isawaitable(result):
            await result

    async def _stream(self, subscriptions, callback=None, authenticated=False, stream_name="broker"):
        """Maintain a broker-native stream with bounded reconnect/backoff.

        The previous adapter returned placeholder dictionaries from streaming
        methods, which made the UI believe a stream existed while no broker
        subscription was actually active. This method owns the persistent
        WebSocket lifecycle and delivers every broker message to the caller.
        """
        backoff = 1.0
        while True:
            ws = None
            try:
                endpoint = await asyncio.to_thread(self._authenticated_ws_url) if authenticated else self.endpoint
                ws = await websockets.connect(
                    endpoint,
                    open_timeout=self.timeout,
                    close_timeout=5,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**20,
                )
                for payload in subscriptions:
                    await ws.send(json.dumps(payload))
                backoff = 1.0
                await self._dispatch_stream(callback, {"msg_type": "stream_status", "stream": stream_name, "status": "connected", "timestamp": time.time()})
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=75)
                    except asyncio.TimeoutError:
                        await ws.send(json.dumps({"ping": 1, "req_id": int(time.time() * 1000) % 2147483647}))
                        continue
                    message = json.loads(raw)
                    await self._dispatch_stream(callback, message)
                    if message.get("error") and message["error"].get("code") in {"AuthorizationRequired", "InvalidToken", "Unauthorized"}:
                        raise BrokerAuthenticationError(message["error"].get("message", "Deriv authentication expired"))
            except asyncio.CancelledError:
                raise
            except BrokerAuthenticationError:
                await self._dispatch_stream(callback, {"msg_type": "stream_status", "stream": stream_name, "status": "authentication_error", "timestamp": time.time()})
                raise
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException, json.JSONDecodeError, BrokerConnectionError) as exc:
                await self._dispatch_stream(callback, {"msg_type": "stream_status", "stream": stream_name, "status": "reconnecting", "error": str(exc), "retry_in": backoff, "timestamp": time.time()})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass

    def _start_stream(self, subscriptions, callback=None, authenticated=False, stream_name="broker"):
        task = asyncio.create_task(self._stream(subscriptions, callback=callback, authenticated=authenticated, stream_name=stream_name))
        return {"status": "streaming", "stream": stream_name, "task": task, "subscriptions": subscriptions}

    async def connect(self):
        start = time.perf_counter()
        account = await self.authenticate()
        latency = (time.perf_counter() - start) * 1000
        self._last_connection_latency = latency
        return {"status": "connected", "account_id": account.get("loginid") or account.get("account_id"), "is_virtual": account.get("is_virtual"), "avatar_url": account.get("avatar_url"), "balance": account.get("balance"), "currency": account.get("currency"), "latency": latency}

    async def disconnect(self):
        return {"status": "disconnected"}

    async def authenticate(self):
        response = await self._request({"balance": 1, "req_id": 1}, authenticated=True)
        balance = response.get("balance") or {}
        loginid = str(balance.get("loginid") or self._account_id())
        broker_virtual = balance.get("is_virtual")
        if broker_virtual is None:
            broker_virtual = response.get("is_virtual")
        configured_type = str((self.credentials or {}).get("account_type") or "demo").lower()
        is_virtual = bool(broker_virtual) if broker_virtual is not None else configured_type == "demo"
        return {"loginid": loginid, "account_id": loginid, "balance": balance.get("balance"), "currency": balance.get("currency"), "is_virtual": is_virtual, "avatar_url": balance.get("avatar_url") or response.get("avatar_url")}

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
        account_id = self._account_id()
        accounts = await self.get_accounts()
        record = next((item for item in accounts if str(item.get("account_id") or item.get("loginid") or "") == account_id), None)
        if record is None:
            raise BrokerAuthenticationError("The selected Deriv account is no longer available to this OAuth credential")
        if record.get("balance") is None:
            account = await self.authenticate()
            return {"account_id": account["account_id"], "balance": account.get("balance"), "currency": account.get("currency"), "account_type": "demo" if account.get("is_virtual") else "real", "avatar_url": account.get("avatar_url")}
        is_virtual = record.get("is_virtual")
        account_type = str(record.get("account_type") or "").lower()
        return {"account_id": str(record.get("account_id") or record.get("loginid") or account_id), "balance": record.get("balance"), "currency": record.get("currency"), "account_type": "demo" if is_virtual is True or account_type == "demo" else "real", "avatar_url": record.get("avatar_url")}

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

    async def get_trade_capabilities(self, symbol):
        response = await self._request({"contracts_for": symbol})
        root = response.get("contracts_for") or {}
        available = root.get("available") or []
        return [item for item in available if isinstance(item, dict) and item.get("contract_type")]

    async def get_chart_history(self, symbol, mode="ticks", count=120, granularity=None):
        count = max(1, min(int(count or 120), 1000))
        if mode == "candles":
            if not granularity:
                raise BrokerOrderError("A broker-supported candle granularity is required")
            payload = {"ticks_history": symbol, "end": "latest", "count": count, "style": "candles", "granularity": int(granularity)}
            candles = (await self._request(payload)).get("candles", [])
            return {"mode": "candles", "symbol": symbol, "granularity": int(granularity), "items": candles}
        payload = {"ticks_history": symbol, "end": "latest", "count": count, "style": "ticks"}
        ticks = (await self._request(payload)).get("history", {})
        return {"mode": "ticks", "symbol": symbol, "items": [{"epoch": e, "quote": q} for e, q in zip(ticks.get("times", []), ticks.get("prices", []))]}

    async def get_chart_capabilities(self):
        return {"modes": ["ticks", "candles"], "timeframes": [{"label": "1m", "seconds": 60}, {"label": "2m", "seconds": 120}, {"label": "5m", "seconds": 300}, {"label": "10m", "seconds": 600}, {"label": "15m", "seconds": 900}, {"label": "30m", "seconds": 1800}, {"label": "1h", "seconds": 3600}, {"label": "2h", "seconds": 7200}, {"label": "4h", "seconds": 14400}, {"label": "8h", "seconds": 28800}, {"label": "1d", "seconds": 86400}], "granularity": {"minimum_seconds": 1, "type": "integer_seconds"}}

    async def subscribe_ticks(self, symbol, callback=None):
        return self._start_stream([{"ticks": symbol, "subscribe": 1, "req_id": 1}], callback=callback, authenticated=False, stream_name=f"ticks:{symbol}")

    async def place_order(self, order):
        routing = order.routing_context or {}
        account_type = str(routing.get("account_type") or self.credentials.get("account_type") or "demo").lower()
        if account_type == "real" and not settings.ALLOW_LIVE_TRADING:
            raise BrokerOrderError("Live-money trading is disabled by platform configuration")
        if str(getattr(order, "order_type", "market") or "market").lower() != "market":
            raise BrokerOrderError("Deriv execution currently supports market contract purchases only")
        requested_contract = str(routing.get("contract_type") or getattr(order, "contract_type", None) or "").upper()
        direction = str(getattr(order, "direction", "") or "").upper()
        if not requested_contract:
            requested_contract = {"BUY": "CALL", "SELL": "PUT", "CALL": "CALL", "PUT": "PUT", "RISE": "RISE", "FALL": "FALL"}.get(direction, "")
        elif requested_contract in {"BUY", "SELL"}:
            requested_contract = {"BUY": "CALL", "SELL": "PUT"}[requested_contract]
        if not requested_contract:
            raise BrokerOrderError("A broker contract type is required")
        live_contracts = await self.get_trade_capabilities(order.symbol)
        allowed = {str(item.get("contract_type") or "").upper() for item in live_contracts}
        if requested_contract not in allowed:
            raise BrokerOrderError(f"Deriv does not currently offer {requested_contract} for {order.symbol}")
        amount = float(order.stake or getattr(order, "quantity", 0) or 0)
        if amount <= 0:
            raise BrokerOrderError("A positive stake is required to place a Deriv order")
        proposal_payload = {"proposal": 1, "amount": amount, "basis": "stake", "contract_type": requested_contract, "currency": routing.get("currency") or getattr(self.account, "currency", None) or "USD", "duration": int(routing.get("duration", 60)), "duration_unit": routing.get("duration_unit", "s"), "underlying_symbol": order.symbol}
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
        buy = (await self._request({"buy": proposal_id, "price": float(ask_price)}, authenticated=True)).get("buy") or {}
        contract_id = buy.get("contract_id")
        if not contract_id:
            raise BrokerOrderError("Deriv accepted the request without returning a contract ID")
        return {"status": "filled", "broker_order_id": str(contract_id), "execution_price": buy.get("buy_price") or ask_price, "fees": 0, "payout": buy.get("payout"), "proposal_id": proposal_id, "contract_type": requested_contract}

    async def modify_order(self, order, **changes):
        raise BrokerOrderError("Use the Deriv contract_update operation for supported open-contract changes")

    async def cancel_order(self, order):
        raise BrokerOrderError("Deriv contracts cannot be cancelled through the generic order API")

    async def close_position(self, position):
        contract_id = getattr(position, "broker_order_id", None)
        if not contract_id:
            raise BrokerOrderError("A Deriv contract id is required to sell a position")
        return await self._request({"sell": int(contract_id), "price": 0}, authenticated=True)

    async def stream_positions(self, callback=None):
        return self._start_stream([{"portfolio": 1, "req_id": 1}, {"transaction": 1, "subscribe": 1, "req_id": 2}], callback=callback, authenticated=True, stream_name="portfolio")

    async def stream_orders(self, callback=None):
        return self._start_stream([{"transaction": 1, "subscribe": 1, "req_id": 1}], callback=callback, authenticated=True, stream_name="transactions")

    async def stream_prices(self, symbols, callback=None):
        symbols = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        if not symbols:
            raise BrokerOrderError("At least one market symbol is required for a price stream")
        subscriptions = [{"ticks": symbol, "subscribe": 1, "req_id": index + 1} for index, symbol in enumerate(dict.fromkeys(symbols))]
        return self._start_stream(subscriptions, callback=callback, authenticated=False, stream_name="ticks")

    async def health_check(self):
        return {"status": "ok", "latency": await self.ping()}

    async def ping(self):
        cached = getattr(self, "_last_connection_latency", None)
        if cached is not None:
            return cached
        start = time.perf_counter()
        await self._request({"ping": 1})
        return (time.perf_counter() - start) * 1000
