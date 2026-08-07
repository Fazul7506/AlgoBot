from .scaffold import ScaffoldBrokerAdapter


class DxtradeAdapter(ScaffoldBrokerAdapter):
    broker_type = 'dxtrade'
    authentication_type = 'session_token'
    asset_classes = ('forex', 'cfd')


Adapter = DxtradeAdapter
