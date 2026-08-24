# AlgoBot Frontend Production Refactor Master Contract

Status: **PHASE 14 COMPLETE AND WORKING**

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
15. Notifications — NEXT
16. Settings
17. Remaining operational/admin pages
18. Global consistency pass
19. Production E2E validation

## Completed phase summaries

### Phase 1 — state/data architecture
Canonical broker lifecycle/state contract, centralized frontend data contract, connected-broker guard, broker event normalization and live broker UI bridge.

### Phase 2 — credential/hardcoded-data elimination
Credential-pattern audit, browser payload sanitization, no silent demo fallback and credential-bearing field removal before browser consumption.

### Phase 3 — shared design system
Global semantic tokens and reusable production primitives.

### Phase 4 — base template
Production shell CSS/JS and runtime guards extracted; centralized navigation/theme/global broker status.

### Phase 5 — broker connection
Generic broker-backed connection surface, canonical connection state, broker catalog, broker-confirmed account type and targeted tests.

### Phase 6 — dashboard
Broker-state KPIs, broker-gated positions/orders/markets, symbol-scoped signals, backend-confirmed kill switch and dashboard contract test.

### Phase 7 — portfolio/positions
Broker-gated positions controller and portfolio dashboard; exposure/P/L/allocation derive only from broker account and positions.

### Phase 8 — orders
Broker-gated execution order controller and execution table.

### Phase 9 — trade history
Authenticated execution history page using broker-backed execution reports with broker order context.

### Phase 10 — market/watchlist
Broker-gated market catalogue/quotes, search, catalogue sync and quote polling with no fabricated prices.

### Phase 11 — charts
Broker-state-gated chart history and authenticated WebSocket market stream with disconnect/reconnect handling.

### Phase 12 — strategies
Broker-gated strategy registry/signals/performance and run/pause/stop lifecycle actions through the centralized backend contract.

### Phase 13 — automation
Broker-aware automation dashboard with workflow/execution state gated on broker connection.

### Phase 14 — workflow templates/builder
Dedicated broker-gated workflow template/builder route, safe starter definitions, backend workflow creation and server-side exclusion of workflow secrets from browser serialization.

See `docs/Architecture/phase-14-workflow-builder.md`.

## Inventory

The complete Phase 0 migration registry is maintained in `docs/Architecture/frontend-template-inventory.md`.

## Merge policy

All phases remain in the single long-lived PR #17. No merge to `main` occurs until every phase is explicitly marked complete and the final production E2E gate passes.

## Phase declaration rule

A phase is not complete merely because code was written. It must have implementation, repository verification, documented exit criteria and an explicit completion declaration. Only then does the next phase begin.
