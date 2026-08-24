# AlgoBot Frontend Production Refactor Master Contract

Status: **PHASE 18 IN PROGRESS**

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
7. Portfolio/Positions — **COMPLETE AND WORKING**
8. Orders — **COMPLETE AND WORKING**
9. Trade history — **COMPLETE AND WORKING**
10. Market/watchlist — **COMPLETE AND WORKING**
11. Charts — **COMPLETE AND WORKING**
12. Strategies — **COMPLETE AND WORKING**
13. Automation — **COMPLETE AND WORKING**
14. Workflow templates/builder — **COMPLETE AND WORKING**
15. Notifications — **COMPLETE AND WORKING**
16. Settings — **COMPLETE AND WORKING**
17. Remaining operational/admin pages — **COMPLETE AND WORKING**
18. Global consistency pass — **IN PROGRESS**
19. Production E2E validation

## Completed phase summaries

### Phase 15 — notifications
Authenticated notification center, persisted preferences, broker-aware state, loading/empty/error handling and notification contract coverage.

### Phase 16 — settings
Authenticated server-backed profile/trading/risk/notification preferences with validation and secret-safe broker separation.

### Phase 17 — remaining operational/admin pages
Remaining identified operational surfaces classified and routed through authenticated application surfaces; pages without genuine broker contracts remain informational or explicitly gated rather than presenting fabricated live trading state.

## Phase 18 — global consistency pass
Audit the accumulated PR for duplicate broker implementations, inconsistent connection states, hardcoded trading/account data, credential exposure, broken routes/navigation, template inheritance defects, REST/WebSocket contract drift, stale/disconnected UI, missing state handling, duplicate CSS/JS, responsive/accessibility regressions, unsafe mutations and test gaps. Phase 18 cannot be declared complete until findings are fixed or explicitly documented as non-blocking with evidence.

## Phase 19 — production E2E validation
Final release gate covering authentication, broker connection/synchronization, account/dashboard, market data, charts/WebSocket lifecycle, positions, orders/execution, history, strategies, automation, notifications, settings, disconnect/reconnect/resynchronization, security and regression coverage. No merge to `main` until this gate passes.

## Inventory

The complete Phase 0 migration registry is maintained in `docs/Architecture/frontend-template-inventory.md`.

## Merge policy

All phases remain in the single long-lived PR #17. No merge to `main` occurs until every phase is explicitly marked complete and the final production E2E gate passes.

## Phase declaration rule

A phase is not complete merely because code was written. It must have implementation, repository verification, documented exit criteria and an explicit completion declaration. Only then does the next phase begin.
