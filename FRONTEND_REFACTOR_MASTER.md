# AlgoBot Frontend Production Refactor Master Contract

Status: **PHASE 2 COMPLETE AND WORKING**

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
3. Shared design system — NEXT
4. `templates/base.html`
5. Broker connection
6. Dashboard
7. Portfolio/Positions
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
- shared backend request wrapper
- broker account retrieval/synchronization
- connected-broker guard
- broker event normalization
- bridge from existing `live_broker_ui.js` to the canonical state

## Phase 2 — credential/hardcoded-data elimination

Implemented:

- repository credential-pattern audit
- frontend broker payload sanitization
- removal of credential-bearing fields before browser consumers receive account JSON
- explicit `unknown` account type when broker data does not provide one, preventing the legacy silent `demo` default from becoming UI truth
- disabled account-switcher messaging changed to a real connection action
- payload guard loaded before `live_broker_ui.js`

The complete Phase 2 audit and controls are recorded in `docs/Architecture/phase-2-credential-and-hardcoded-data.md`.

## Inventory

The complete Phase 0 template/domain migration registry is maintained in `docs/Architecture/frontend-template-inventory.md`.

## Merge policy

All phases remain in this single long-lived PR. No merge to `main` occurs until every phase is explicitly marked complete and the final production E2E gate passes.

## Phase declaration rule

A phase is not considered complete merely because code was written. It must have its implementation, repository verification, documented exit criteria and explicit completion declaration. Then, and only then, the next phase begins.
