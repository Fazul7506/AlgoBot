from .scaffold import ScaffoldBrokerAdapter


class IcMarketsAdapter(ScaffoldBrokerAdapter):
    broker_type = 'ic_markets'
    authentication_type = 'metatrader_or_ctrader'
    asset_classes = ('forex', 'cfd')


Adapter = IcMarketsAdapter
