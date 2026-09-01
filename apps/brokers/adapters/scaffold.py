"""Explicitly unsupported broker adapter base.

These adapters are intentionally *not* paper-trading adapters.  Until a real
vendor integration is implemented, every operation fails explicitly so an
unsupported broker can never masquerade as a working paper/live connection.
"""
from .base import BrokerAdapter


class BrokerAdapterNotImplemented(RuntimeError):
    """Raised when a broker has no production connector yet."""


class ScaffoldBrokerAdapter(BrokerAdapter):
    """Fail-closed adapter for brokers without a real integration."""

    broker_type = "scaffold"
    authentication_type = "broker_specific"
    supports_streaming = False
    asset_classes = ()
    is_production_ready = False

    def _unsupported(self, operation):
        raise BrokerAdapterNotImplemented(
            f"{self.broker_type} broker adapter does not implement {operation}. "
            "Configure a supported production adapter or complete the vendor integration first."
        )

    async def connect(self): return self._unsupported("connect")
    async def disconnect(self): return self._unsupported("disconnect")
    async def authenticate(self): return self._unsupported("authenticate")
    async def refresh_token(self): return self._unsupported("refresh_token")
    async def get_accounts(self): return self._unsupported("get_accounts")
    async def get_balance(self): return self._unsupported("get_balance")
    async def get_positions(self): return self._unsupported("get_positions")
    async def get_orders(self): return self._unsupported("get_orders")
    async def get_open_orders(self): return self._unsupported("get_open_orders")
    async def get_trade_history(self, **filters): return self._unsupported("get_trade_history")
    async def get_market_data(self, symbol, **params): return self._unsupported("get_market_data")
    async def subscribe_ticks(self, symbol, callback=None): return self._unsupported("subscribe_ticks")
    async def place_order(self, order): return self._unsupported("place_order")
    async def modify_order(self, order, **changes): return self._unsupported("modify_order")
    async def cancel_order(self, order): return self._unsupported("cancel_order")
    async def close_position(self, position): return self._unsupported("close_position")
    async def stream_positions(self, callback=None): return self._unsupported("stream_positions")
    async def stream_orders(self, callback=None): return self._unsupported("stream_orders")
    async def stream_prices(self, symbols, callback=None): return self._unsupported("stream_prices")
    async def health_check(self): return self._unsupported("health_check")
    async def ping(self): return self._unsupported("ping")
