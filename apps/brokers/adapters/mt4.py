from .scaffold import ScaffoldBrokerAdapter


class Mt4Adapter(ScaffoldBrokerAdapter):
    broker_type = 'mt4'
    authentication_type = 'username_password'
    asset_classes = ('forex', 'cfd')


Adapter = Mt4Adapter
