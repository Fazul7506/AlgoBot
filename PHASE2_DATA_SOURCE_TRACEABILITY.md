# Phase 2 data-source traceability

This document describes the source of the values returned by the broker and
market-data APIs.  A missing broker value remains absent; it is never replaced
with a synthetic value.

| Frontend value | API / service path | Authoritative source |
| --- | --- | --- |
| Account identifier, balance, currency, account type | `POST /api/brokers/accounts/{id}/sync/` → `SynchronizationService` → `DerivAdapter.get_balance()` | Authenticated Deriv `authorize` response |
| Equity, margin, free margin | Account sync → `SynchronizationService` | Broker response only when the adapter returns that field |
| Broker connection state and latency | `POST /api/brokers/connect/` → `BrokerConnectionService` → `DerivAdapter.ping()` | Deriv `ping` response and measured request latency |
| Open positions / contracts | `GET /api/positions/` | User-owned synchronized `Position` records; Deriv adapter obtains live contracts from `portfolio` when synchronization is implemented for a contract type |
| Orders, executions and reconciliation | `GET /api/orders/`, `GET /api/executions/`, `GET /api/reconciliation/` | User-owned platform records; no generated trade history |
| Broker transaction history | `DerivAdapter.get_trade_history()` | Authenticated Deriv `statement` response |
| Tick, bid, ask, spread and tick time | `/api/ticks/*` and market stream → `TickService` | Ingested broker tick; spread is computed from that tick's bid and ask |
| Candles / price history | `/api/candles/*` → `CandleService` | OHLC aggregation of ingested live ticks |
| Market status and symbols | `/api/markets/*` | Active, broker-synchronized market symbol records; unavailable data is represented by an empty response rather than invented prices |

REST is used for account synchronization, historical records, and CRUD data.
The WebSocket manager owns a single connection per manager instance for live
ticks, de-duplicates subscriptions, re-subscribes after reconnect, and closes
its listener during cleanup.  It does not open a background connection during a
REST request.
