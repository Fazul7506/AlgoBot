from .scaffold import ScaffoldBrokerAdapter


class CtraderAdapter(ScaffoldBrokerAdapter):
    broker_type = 'ctrader'
    authentication_type = 'oauth'
    asset_classes = ('forex', 'cfd')


Adapter = CtraderAdapter
