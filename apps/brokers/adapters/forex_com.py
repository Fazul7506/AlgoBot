from .scaffold import ScaffoldBrokerAdapter


class ForexComAdapter(ScaffoldBrokerAdapter):
    broker_type = 'forex_com'
    authentication_type = 'username_password'
    asset_classes = ('forex', 'cfd')


Adapter = ForexComAdapter
