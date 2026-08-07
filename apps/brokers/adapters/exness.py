from .scaffold import ScaffoldBrokerAdapter


class ExnessAdapter(ScaffoldBrokerAdapter):
    broker_type = 'exness'
    authentication_type = 'api_key_or_session'
    asset_classes = ('forex', 'cfd')


Adapter = ExnessAdapter
