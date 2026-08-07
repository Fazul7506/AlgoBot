# Deriv Adapter

Deriv is the first production broker adapter, not the platform foundation.

- Adapter module: `apps/brokers/adapters/deriv.py`.
- Authentication: OAuth, handled as broker-specific adapter behavior.
- WebSocket/API details must remain isolated in Deriv adapter modules.
- Platform URLs should remain broker-neutral, such as `/brokers/connect/`, `/brokers/manage/`, `/brokers/accounts/`, `/brokers/settings/`, and `/brokers/status/`.
