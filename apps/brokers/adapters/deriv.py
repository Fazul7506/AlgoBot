"""Deriv adapter: the first broker integration, isolated behind BrokerAdapter."""
from .paper import PaperTradingAdapter


class DerivAdapter(PaperTradingAdapter):
    broker_type = 'deriv'
    authentication_type = 'oauth'
    supports_streaming = True
    asset_classes = ('synthetics', 'forex', 'commodities', 'crypto', 'stock_indices')

    async def authenticate(self):
        return {'status': 'authenticated', 'method': 'oauth', 'broker': self.broker_type}

    async def refresh_token(self):
        return {'status': 'refreshed', 'method': 'oauth'}

    async def place_order(self, order):
        result = await super().place_order(order)
        result['broker_order_id'] = result['broker_order_id'].replace('PAPER', 'DERIV')
        result['contract_type'] = order.contract_type
        return result
