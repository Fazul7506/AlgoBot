"""Deriv broker adapter. All Deriv API access is isolated in this module."""
from typing import Any
from .websocket import DerivWebSocketEngine

class DerivAdapter:
    def __init__(self, broker_account=None, engine: DerivWebSocketEngine | None = None):
        self.broker_account = broker_account; self.engine = engine or DerivWebSocketEngine()
    async def connect(self) -> None: await self.engine.connect()
    async def disconnect(self) -> None: await self.engine.disconnect()
    async def authorize(self) -> str:
        token = self.broker_account.token.get_access_token() if self.broker_account and hasattr(self.broker_account, "token") else ""
        return await self.engine.authorize(token)
    async def refresh_token(self) -> dict[str, Any]: return {"status": "refresh_not_required_for_pat"}
    async def buy_contract(self, **payload): return {"req_id": await self.engine.request({"buy": 1, **payload})}
    async def sell_contract(self, contract_id: str, price: float | None = None):
        payload = {"sell": contract_id};
        if price is not None: payload["price"] = price
        return {"req_id": await self.engine.request(payload)}
    async def proposal(self, **payload): return {"req_id": await self.engine.request({"proposal": 1, **payload})}
    async def proposal_open_contract(self, contract_id: str): return {"req_id": await self.engine.request({"proposal_open_contract": 1, "contract_id": contract_id})}
    async def ticks(self, symbol: str): return await self.engine.subscribe(symbol)
    async def candles(self, symbol: str, granularity: int = 60): return {"req_id": await self.engine.request({"ticks_history": symbol, "style": "candles", "granularity": granularity, "subscribe": 1})}
    async def balance(self): return {"req_id": await self.engine.request({"balance": 1, "subscribe": 1})}
    async def active_symbols(self): return {"req_id": await self.engine.request({"active_symbols": "brief", "product_type": "basic"})}
    async def portfolio(self): return {"req_id": await self.engine.request({"portfolio": 1})}
    async def statement(self, **filters): return {"req_id": await self.engine.request({"statement": 1, **filters})}
    async def profit_table(self, **filters): return {"req_id": await self.engine.request({"profit_table": 1, **filters})}
    async def transaction_history(self, **filters): return {"req_id": await self.engine.request({"transaction": 1, **filters})}
    async def buy(self, **payload): return await self.buy_contract(**payload)
    async def sell(self, **payload): return await self.sell_contract(**payload)
    async def history(self, **filters): return await self.statement(**filters)
    async def positions(self): return await self.portfolio()
    async def orders(self): return await self.profit_table()
    async def subscribe_ticks(self, symbol: str): return await self.ticks(symbol)
