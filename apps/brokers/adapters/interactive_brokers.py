from .scaffold import ScaffoldBrokerAdapter


class InteractiveBrokersAdapter(ScaffoldBrokerAdapter):
    broker_type = 'interactive_brokers'
    authentication_type = 'session_gateway'
    asset_classes = ('equities', 'options', 'futures', 'forex')


Adapter = InteractiveBrokersAdapter
