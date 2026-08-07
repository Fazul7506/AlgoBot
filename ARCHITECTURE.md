# AlgoBot Enterprise Architecture

AlgoBot is a standalone institutional trading platform. Brokers are interchangeable execution providers and never define platform architecture.

## Layering

Presentation Layer → Application Layer → Trading Core → Broker Abstraction Layer → Broker Adapters → Broker APIs

- Presentation Layer: templates, static assets, dashboards, broker marketplace, terminal.
- Application Layer: Django views, serializers, API endpoints, orchestration services.
- Trading Core: execution, portfolio, risk, analytics, AI, automation, and notifications.
- Broker Abstraction Layer: `apps.brokers.adapters.base.BrokerAdapter`, `BrokerRegistry`, `BrokerManager`.
- Broker Adapters: isolated broker implementations under `apps/brokers/adapters/`.
- Broker APIs: external broker HTTP/WebSocket/OAuth/API-key systems.

The Trading Core must never import Deriv or any other broker module directly. It calls the Broker Interface through the Broker Manager/Registry.
