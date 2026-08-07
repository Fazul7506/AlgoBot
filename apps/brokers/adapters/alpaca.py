from .scaffold import ScaffoldBrokerAdapter


class AlpacaAdapter(ScaffoldBrokerAdapter):
    broker_type = 'alpaca'
    authentication_type = 'api_key_secret'
    asset_classes = ('equities', 'crypto')


Adapter = AlpacaAdapter
