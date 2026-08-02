# Strategy Engine

Phase 6 adds a broker-independent strategy app under `apps/strategies`. Strategies consume market/indicator context and return execution intents; order placement must be delegated to the Trading/Execution Engine.
