class BrokerError(Exception): pass
class BrokerConnectionError(BrokerError): pass
class BrokerAuthenticationError(BrokerError): pass
class BrokerOrderError(BrokerError): pass
class BrokerRoutingError(BrokerError): pass
class BrokerReconciliationError(BrokerError): pass
