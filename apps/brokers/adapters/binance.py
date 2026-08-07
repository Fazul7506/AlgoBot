from .scaffold import ScaffoldBrokerAdapter


class BinanceAdapter(ScaffoldBrokerAdapter):
    broker_type = 'binance'
    authentication_type = 'api_key_secret'
    asset_classes = ('crypto',)


Adapter = BinanceAdapter
