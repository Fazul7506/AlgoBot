# AlgoBot V2 Implementation Plan

## Objective
Upgrade AlgoBot into an advanced professional trading platform while preserving all currently working broker, market-data, AI, risk, execution, portfolio, billing, authentication, and monitoring functionality.

## Non-negotiable preservation rules
- Do not replace a working broker integration with mock or generated data.
- Do not weaken or bypass risk validation, broker-authoritative contract validation, authentication, account scoping, or execution controls.
- Do not change existing API contracts unless a compatibility path is retained.
- Do not remove existing pages/routes until their replacement is implemented and verified.
- Demo and real accounts must remain explicitly separated.
- Broker state is authoritative for account, quote, contract, order, and position facts.
- AI recommendations must remain subordinate to risk and execution validation.
- Every functional UI change must have a clear fallback/error state.

## Phase 0 — Baseline and safety
- [x] Create isolated `algobot-v2-foundation` branch from `main`.
- [ ] Record current route/page inventory.
- [ ] Record current broker/market/AI/risk/execution API contracts.
- [ ] Identify existing automated tests and critical execution tests.
- [ ] Verify current terminal, broker account loading, contract loading, market data, order validation and execution before UI refactors.

## Phase 1 — Trading foundation
- [ ] Strengthen broker/account state model and global account selector.
- [ ] Make LIVE/DEMO/REAL states impossible to confuse.
- [ ] Harden market-data freshness and streaming state.
- [ ] Harden order idempotency, retries and broker reconciliation.
- [ ] Preserve existing Deriv-native market/contract behavior.
- [ ] Add regression coverage before changing terminal behavior.

## Phase 2 — Professional Trading Terminal
- [ ] Upgrade terminal layout without changing execution semantics.
- [ ] Add richer chart controls and market context.
- [ ] Add order preview with risk/AI/broker gates.
- [ ] Expose execution status and authoritative broker state.
- [ ] Add mobile-focused terminal behavior.

## Phase 3 — Market Intelligence
- [ ] Upgrade Markets page.
- [ ] Add Market Scanner.
- [ ] Add signal lifecycle and confluence views.

## Phase 4 — Quant Research
- [ ] Upgrade Strategies.
- [ ] Add Strategy Builder.
- [ ] Upgrade Backtesting with robust metrics and validation.
- [ ] Add Data Center and data-quality views.
- [ ] Add Trade Journal.

## Phase 5 — AI Intelligence
- [ ] Upgrade AI Predictions.
- [ ] Add Model Lab.
- [ ] Add model versioning, explainability, calibration and drift views.
- [ ] Ensure AI remains advisory/gated by risk and execution.

## Phase 6 — Operations
- [ ] Upgrade Risk.
- [ ] Upgrade Monitoring/Mission Control.
- [ ] Upgrade Notifications into Alert Center.
- [ ] Add Automation.
- [ ] Add Bot Runtime/Deployments.
- [ ] Add Audit Log.
- [ ] Add Security Center.

## Phase 7 — Portfolio and analytics
- [ ] Upgrade Portfolio.
- [ ] Upgrade Analytics.
- [ ] Upgrade Performance with distinct responsibilities.
- [ ] Upgrade Trade History with trade post-mortems.

## Phase 8 — Integrations and SaaS
- [ ] Upgrade Brokers capability/status UI.
- [ ] Only label adapters as production when actually implemented and verified.
- [ ] Upgrade Billing without coupling billing state to trading execution.
- [ ] Add developer/API workspace when stable.

## Definition of done
A phase is complete only when:
1. Existing functionality still works.
2. Existing API behavior is preserved or compatibility is explicitly provided.
3. New behavior has automated regression coverage where practical.
4. Broker-authoritative facts remain broker-authoritative.
5. No mock data is introduced into live trading paths.
6. Failure, stale-data, disconnected and unavailable states are explicit.
7. Demo/real account boundaries remain safe.
