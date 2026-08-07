# Phase 13 Broker Architecture

Phase 13 introduces a broker-agnostic execution architecture centered on the apps.brokers Django app.

## Scope

- Broker adapters implement the BrokerAdapter interface.
- Deriv and paper trading are available without Trading Engine broker-specific logic.
- OMS, EMS, SOR, failover, synchronization, reconciliation, latency, and health services are exposed through the broker service layer.

## Extension Model

Add a broker by creating a new adapter in apps/brokers/adapters/ and registering it with BrokerRegistry.
