"""Broker-neutral adapters for the legacy broker service layer."""

from decimal import Decimal
from uuid import uuid4


class PaperBrokerAdapter:
    """Safe default adapter that supports broker-layer methods without a vendor."""

    def __init__(self, broker=None, account=None, credentials=None):
        self.broker = broker
        self.account = account
        self.credentials = credentials or {}
        self.connected = False

    async def connect(self):
        self.connected = True
        return {"status": "connected"}

    async def disconnect(self):
        self.connected = False
        return {"status": "disconnected"}

    async def refresh_token(self):
        return {"status": "not_required"}

    async def buy(self, **payload):
        return self._execution_response("buy", payload)

    async def sell(self, **payload):
        return self._execution_response("sell", payload)

    async def balance(self):
        return {
            "balance": getattr(self.account, "balance", Decimal("0")),
            "currency": getattr(self.account, "currency", "USD"),
        }

    async def history(self, **filters):
        return {"history": [], "filters": filters}

    async def positions(self):
        return []

    async def orders(self):
        return []

    async def subscribe_ticks(self, symbol: str):
        return {"subscription": "ticks", "symbol": symbol}

    @staticmethod
    def _execution_response(direction, payload):
        return {
            "order_id": f"PAPER-{uuid4().hex[:12]}",
            "status": "executed",
            "direction": direction,
            "payload": payload,
        }
