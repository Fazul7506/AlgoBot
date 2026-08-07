from .scaffold import ScaffoldBrokerAdapter


class PepperstoneAdapter(ScaffoldBrokerAdapter):
    broker_type = 'pepperstone'
    authentication_type = 'metatrader_or_ctrader'
    asset_classes = ('forex', 'cfd')


Adapter = PepperstoneAdapter
