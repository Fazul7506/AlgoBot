from .scaffold import ScaffoldBrokerAdapter


class MetatraderGatewayAdapter(ScaffoldBrokerAdapter):
    broker_type = 'metatrader_gateway'
    authentication_type = 'username_password'
    asset_classes = ('forex', 'cfd')


Adapter = MetatraderGatewayAdapter
