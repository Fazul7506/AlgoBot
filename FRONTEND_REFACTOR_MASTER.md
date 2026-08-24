# AlgoBot Frontend Production Refactor Master Contract

Status: **PHASE 6 COMPLETE AND WORKING**

Branch: `refactor/frontend-production-foundation`
Long-lived PR: `#17`
Base: `main`

## Non-negotiable product invariant

The broker is the source of truth for broker-backed trading state.

`Broker -> Broker Adapter/Manager -> Django service/API -> REST/WebSocket -> Frontend state -> Template/Page -> User command -> Django -> Broker -> confirmed result -> Frontend state`

The frontend must never manufacture trading reality.

Before a broker connection is established, broker-backed UI must not show invented balances, equity, positions, orders, prices, P/L, account identity, or live status. After connection, those values must be traceable to backend/broker state.

## Page/template production gate

A page advances only when all applicable checks pass:

- route/view renders
- template inheritance is correct
- real backend data contract identified
- broker dependency identified
- no hardcoded trading/account/credential data
- loading/empty/error/no-broker/disconnected/reconnecting states handled
- mutations travel backend -> broker and UI changes only from confirmed state
- REST/WebSocket lifecycle is correct
- permissions/authentication enforced
- desktop/tablet/mobile acceptable
- keyboard/focus/accessibility acceptable
- no console/runtime errors introduced
- automated checks/CI pass

Target: **L5 Production**. Foundational surfaces may reach **L6 Reference**.

## Refactor sequence / phase ledger

0. Repository/template inventory — **COMPLETE**
1. Frontend state/data architecture — **COMPLETE AND WORKING**
2. Credential and hardcoded-data elimination — **COMPLETE AND WORKING**
3. Shared design system — **COMPLETE AND WORKING**
4. `templates/base.html` — **COMPLETE AND WORKING**
5. Broker connection — **COMPLETE AND WORKING**
6. Dashboard — **COMPLETE AND WORKING**
7. Portfolio/Positions — NEXT
8. Orders
9. Trade history
10. Market/watchlist
11. Charts
12. Strategies
13. Automation
14. Workflow templates/builder
15. Notifications
16. Settings
17. Remaining operational/admin pages
18. Global consistency pass
19. Production E2E validation

## Phase 1 — state/data architecture

Implemented globally:

- `window.AlgoBotBrokerState`
- lifecycle states: `NO_BROKER`, `CONNECTING`, `CONNECTED`, `SYNCING`, `READY`, `DEGRADED`, `DISCONNECTED`, `RECONNECTING`, `ERROR`
- broker/account/balance/position/order/trade/market/strategy/automation/notification state
- subscriptions and `algobot:state-changed`
- `window.AlgoBotFrontendData`
- shared backend request wrapper, broker account retrieval/synchronization, connected-broker guard and broker-event normalization
- bridge from `live_broker_ui.js` to canonical state

## Phase 2 — credential/hardcoded-data elimination

Implemented credential-pattern audit, browser payload sanitization, removal of credential-bearing fields from browser account JSON, explicit `unknown` account type, connection-first account switching and payload guard ordering.

## Phase 3 — shared design system

Implemented `static/css/design_system.css` with shared spacing/radius/surface/text/border tokens, semantic broker/status states, cards, buttons, fields, state panels, skeletons, focus, mobile sizing and reduced-motion behavior.

## Phase 4 — base template production shell

Implemented `static/css/base_shell.css`, `static/js/base_shell.js`, `static/js/core/api_execution_guard.js`, dependency-ordered global bootstrap, extracted inline shell styles/runtime guards, centralized navigation/theme/global broker indicator, and preserved page extension points.

## Phase 5 — broker connection

Implemented generic broker-backed connection page, canonical connection status UI, backend broker catalog, broker-confirmed account type enforcement, and targeted connection contract tests.

## Phase 6 — dashboard

Implemented `static/js/dashboard.js` and refactored `templates/core/dashboard.html` so account KPIs come from canonical broker state, broker-backed positions/orders/market data use the centralized frontend contract, no-broker/disconnected states are explicit, signals use a backend-selected broker symbol, and kill-switch success is shown only after backend confirmation.

Net P/L remains unavailable until the canonical backend account contract exposes a broker-confirmed P/L field; no unrelated local trade statistic is substituted.

See `docs/Architecture/phase-6-dashboard.md`.

## Inventory

The complete Phase 0 migration registry is maintained in `docs/Architecture/frontend-template-inventory.md`.

## Merge policy

All phases remain in the single long-lived PR #17. No merge to `main` occurs until every phase is explicitly marked complete and the final production E2E gate passes.

## Phase declaration rule

A phase is not complete merely because code was written. It must have implementation, repository verification, documented exit criteria and an explicit completion declaration. Only then does the next phase begin.
