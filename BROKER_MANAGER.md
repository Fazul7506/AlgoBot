# Broker Manager

`apps.brokers.services.BrokerManager` owns broker lifecycle and selection.

Responsibilities:

- Load and register brokers dynamically through `BrokerRegistry` import paths.
- Seed supported production and scaffold brokers.
- Enable and disable brokers.
- Manage active connections using `BrokerConnectionService`.
- Reconnect and heartbeat monitoring.
- Health monitoring and latency tracking.
- Failover and default account/broker selection.
- Multi-account routing through `SmartOrderRouter`.
- Broker-specific authentication through `AuthenticationService`.
