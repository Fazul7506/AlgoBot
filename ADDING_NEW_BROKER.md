# Adding a New Broker

1. Add a module in `apps/brokers/adapters/<broker_type>.py`.
2. Implement `BrokerAdapter` directly, or extend `ScaffoldBrokerAdapter` while building.
3. Define `broker_type`, `authentication_type`, streaming support, and asset classes.
4. Register the adapter import path in `BrokerRegistry.adapter_paths` or call `BrokerManager.register_broker`.
5. Add marketplace metadata in `BrokerManager.broker_catalog`.
6. Keep all vendor SDK, OAuth, websocket, market data, and order translation code inside the adapter.
7. Do not modify `ExecutionEngine`, `RiskEngine`, `PortfolioEngine`, analytics, AI, automation, or notifications.
