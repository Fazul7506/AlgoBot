"""Compatibility facade for the canonical broker-neutral Deriv adapter.

New code must import ``apps.brokers.adapters.deriv.DerivAdapter``. This facade
contains only migration shims for older callers and does not implement another
broker connection.
"""
from apps.brokers.adapters.deriv import DerivAdapter as _CanonicalDerivAdapter


class DerivAdapter(_CanonicalDerivAdapter):
    """Legacy constructor/API mapped onto the single canonical adapter."""

    def __init__(self, broker_account=None, engine=None):
        super().__init__(broker=None, account=broker_account, credentials={})
        self.broker_account = broker_account
        self.engine = engine

    async def authorize(self):
        await self.authenticate()
        return self._account_id()

    async def balance(self):
        return await self.get_balance()

    async def portfolio(self):
        return {"contracts": await self.get_positions()}

    async def statement(self, **filters):
        return {"transactions": await self.get_trade_history(**filters)}

    async def transaction_history(self, **filters):
        return await self.statement(**filters)

    async def profit_table(self, **filters):
        return {"transactions": await self.get_trade_history(**filters)}

    async def ticks(self, symbol):
        if self.engine is not None:
            if hasattr(self.engine, "subscribe_ticks"):
                return await self.engine.subscribe_ticks(symbol)
            if hasattr(self.engine, "subscribe"):
                return await self.engine.subscribe(symbol)
        return await self.get_market_data(symbol)

    async def candles(self, symbol, granularity=60):
        return await self.get_market_data(symbol, granularity=granularity)

    async def active_symbols(self):
        return await self.get_accounts()

    async def buy_contract(self, price, parameters):
        if self.engine is not None and hasattr(self.engine, "request"):
            payload = dict(parameters or {})
            payload.update({"buy": price})
            return await self.engine.request(payload)
        if self.engine is not None and hasattr(self.engine, "buy_contract"):
            return await self.engine.buy_contract(price=price, parameters=parameters)
        raise RuntimeError("Legacy buy_contract() requires a broker execution engine")

    async def buy(self, **payload):
        raise RuntimeError("Legacy buy() is retired; route orders through the platform execution engine")

    async def sell(self, **payload):
        raise RuntimeError("Legacy sell() is retired; route orders through the platform execution engine")

    async def history(self, **filters):
        return await self.get_trade_history(**filters)

    async def positions(self):
        return await self.get_positions()

    async def orders(self):
        return await self.get_orders()
