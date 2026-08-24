# AlgoBot Frontend Production Refactor Master Contract

Status: **PHASE 9 COMPLETE AND WORKING**

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
10. Market/watchlist — NEXT
11. Charts
12. Strategies
13. Automation
14. Workflow templates/builder
15. Notifications
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
Global semantic tokens and reusable production primitives for status, cards, buttons, fields, states, skeletons, focus, mobile sizing and reduced motion.

### Phase 4 — base template
Production shell CSS/JS and runtime guards extracted from `base.html`; centralized navigation/theme/global broker status.

### Phase 5 — broker connection
Generic broker-backed connection surface, canonical connection state, broker catalog, broker-confirmed account type and targeted tests.

### Phase 6 — dashboard
Broker-state KPIs, broker-gated positions/orders/markets, symbol-scoped signals, backend-confirmed kill switch and dashboard contract test.

### Phase 7 — portfolio/positions
Broker-gated positions controller and portfolio dashboard. Portfolio exposure/P/L/allocation derive only from broker account and position data.

### Phase 8 — orders
Broker-gated execution order controller and order page. Order status is inspected from backend execution records; no frontend mutation pretends an order was cancelled/filled.

### Phase 9 — trade history
Added authenticated `/trade-history/`, broker-backed execution history controller, navigation entry and enriched execution report serializer with symbol/direction/broker order context. Targeted template test added.

See `docs/Architecture/phase-9-trade-history.md`.

## Inventory

The complete Phase 0 migration registry is maintained in `docs/Architecture/frontend-template-inventory.md`.

## Merge policy

All phases remain in the single long-lived PR #17. No merge to `main` occurs until every phase is explicitly marked complete and the final production E2E gate passes.

## Phase declaration rule

A phase is not complete merely because code was written. It must have implementation, repository verification, documented exit criteria and an explicit completion declaration. Only then does the next phase begin.
