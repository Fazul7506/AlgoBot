"""Scaffold adapters for brokers whose production connectors are not implemented yet."""
from .paper import PaperTradingAdapter


class ScaffoldBrokerAdapter(PaperTradingAdapter):
    broker_type = 'scaffold'
    authentication_type = 'broker_specific'
    asset_classes = ()

    async def connect(self):
        return {'status': 'coming_soon', 'broker': self.broker_type}

    async def authenticate(self):
        return {'status': 'coming_soon', 'method': self.authentication_type, 'broker': self.broker_type}

    async def place_order(self, order):
        return {'status': 'rejected', 'reason': f'{self.broker_type} adapter is scaffold-only'}
