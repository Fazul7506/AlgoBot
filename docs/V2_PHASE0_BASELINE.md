# AlgoBot V2 Phase 0 Baseline

Date: 2026-08-28
Branch: `algobot-final-hardening`
Pull request: #57

## Scope

Phase 0 establishes the verification baseline before the remaining V2 hardening work. It records the authoritative route/API/test/CI surface and the known-good commit used as the starting point for Phase 1.

## Baseline commit

PR #57 head before Phase 1 changes:

`2ef75a86bc64ebdd43332bc8a23c8528727fde82`

The branch was 5 commits ahead of `main` and 0 behind when the V2 plan was reconciled.

## Route/page inventory

The project exposes the authenticated trading foundation through the `apps.brokers` API surface:

- `/brokers/`
- `/brokers/accounts/`
- `/brokers/accounts/<id>/`
- `/brokers/accounts/<id>/select/`
- `/brokers/accounts/<id>/sync/`
- `/brokers/connect/`
- `/brokers/disconnect/`
- `/brokers/connections/`
- `/orders/`
- `/executions/`
- `/positions/`
- `/reconciliation/`
- `/broker-health/`

The V2 branch also retains the existing authenticated dashboard, terminal, markets, signals, strategies, backtesting, AI, risk, portfolio, monitoring, automation, analytics, billing, developer and broker modules. This phase does not replace those contracts.

## API contract inventory

Trading-foundation contracts are backend-authoritative:

1. Broker catalog and capability metadata are read from `Broker`.
2. Broker accounts are user-scoped through `BrokerAccount.user`.
3. The global account selector is represented by `BrokerAccount.is_preferred` and is mutated atomically by the account `select` action.
4. Connection state is account-scoped through `BrokerConnection.broker_account`.
5. Orders are user/account scoped and carry `client_order_id`, `broker_order_id`, `routing_context`, status and timestamps.
6. Unknown execution outcomes are persisted as `pending` plus a `TradeReconciliation` record rather than being silently retried.
7. Market freshness is derived from persisted `MarketSnapshot.timestamp`; execution must not invent a quote.
8. Deriv account type is confirmed from broker synchronization/connection data and is not accepted from the client as authoritative.

## Automated-test / CI inventory

The PR head had three successful GitHub Actions runs at the baseline commit:

- Template Validation — run `33157700985`, success.
- Validate Django Migrations — run `33157701011`, success.
- Production Validation — run `33157701005`, success.

The Phase 1 change set adds `apps/brokers/test_phase1_hardening.py` for regression coverage of:

- preferred/global broker-account selection;
- demo/real environment mismatch rejection;
- live-money gating;
- fresh market snapshot acceptance;
- stale market snapshot rejection.

## Baseline verification policy

A feature is not marked complete merely because the code exists. The PR must retain green Django/template/migration/production validation after each hardening increment. Unknown broker execution states must remain reconciliable and must never be converted into an automatic duplicate broker order.

## Phase 0 status

- Route/page inventory: complete.
- API contract inventory: complete.
- Automated-test/CI inventory: complete.
- Baseline execution verification: complete at the recorded baseline commit; the Phase 1 commits must now establish a new green post-change baseline.
