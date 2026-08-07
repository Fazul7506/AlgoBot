from .scaffold import ScaffoldBrokerAdapter


class BybitAdapter(ScaffoldBrokerAdapter):
    broker_type = 'bybit'
    authentication_type = 'api_key_secret'
    asset_classes = ('crypto', 'derivatives')


Adapter = BybitAdapter
