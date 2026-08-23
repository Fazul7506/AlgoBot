# AlgoBot Architecture

AlgoBot is a broker-independent trading platform. Frontends call Django APIs and WebSockets; trading services call the broker manager; broker adapters own vendor-specific protocols.

Canonical flow:

Frontend ↕ Backend/API ↕ Trading Core ↕ Broker Manager ↕ Broker Adapter ↕ Broker
