from .scaffold import ScaffoldBrokerAdapter


class OandaAdapter(ScaffoldBrokerAdapter):
    broker_type = 'oanda'
    authentication_type = 'api_token'
    asset_classes = ('forex', 'cfd')


Adapter = OandaAdapter
